"""CLI tool: HCMUS course registration (new-portalX.hcmus.edu.vn).

Commands:
  python run.py mirrors                 check which of the 20 mirrors are up
  python run.py login [--mirror N]      auto-login (anticaptcha.top / 2captcha), save cookies
  python run.py login --all [--force]   auto-login TẤT CẢ mirror đang sống (lưu kho cookie
                                       dự phòng cho race; bỏ qua mirror đã có cookie sống)
  python run.py login-manual            login tay qua browser cho mọi mirror
                                       [--mirrors 4,11|1-20] [--force]
  python run.py cookie [--mirror N]     paste cookies from your browser instead
                                       (hoặc dán thẳng vào .env: PORTAL{N}_ASPXAUTH)
  python run.py sessions                trạng thái cookie đã lưu (sống/chết)
  python run.py status [--mirror N]     show registered + open classes
  python run.py open [--mirror N]       mở sẵn trang ĐKHP trên mirror nhanh nhất
                                       có cookie sống — tự F5 khi nghẽn, phiên chết
                                       tự login lại, cổng nghẽn đặc thì tự chuyển
                                       cổng; bạn chỉ việc gõ 6 số + bấm
  python run.py register [--codes A,B] [--dry-run]   register ALL open classes (or subset)
  python run.py cancel --codes A,B      cancel registrations
  python run.py race [--codes A,B]      loop until classes open, register instantly

Config lives in .env next to this file (see .env.example).
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

import httpx
from dotenv import load_dotenv

import captchasvc
import cookiestore
import solver_anticaptcha
import portal as P
from portal import PortalSession

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

USERNAME = os.getenv("USERNAME_SV", "")
PASSWORD = os.getenv("PASSWORD_SV", "")
MIRROR = int(os.getenv("MIRROR", "0") or 0)  # 0 = auto (fastest alive)
POLL = float(os.getenv("POLL_INTERVAL", "1.0"))


def log(msg: str):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def load_session(mirror: int = 0) -> PortalSession:
    m = mirror or MIRROR
    if not m:
        raise SystemExit("No mirror selected. Run `python run.py mirrors`, set MIRROR in .env, "
                         "or pass --mirror N.")
    cookies = cookiestore.load(m)
    if cookies:
        log(f"loaded cookies for new-portal{m} (nguồn: {cookiestore.source(m)})")
    return PortalSession(m, cookies=cookies, log=log)


def save_session(s: PortalSession):
    cookiestore.save(s.mirror, s.cookie_dict())
    log(f"cookies saved for new-portal{s.mirror}")
    for c in s.client.cookies.jar:
        if c.name == ".ASPXAUTH" and c.expires:
            log(f"  (.ASPXAUTH hết hạn lúc: "
                f"{time.strftime('%H:%M:%S %d/%m/%Y', time.localtime(c.expires))})")
            break


def ensure_ready(s: PortalSession) -> str:
    """Pass the captcha gate; auto re-login qua dịch vụ giải captcha nếu mất auth."""
    try:
        return s.pass_gate()
    except P.LoginFailed:
        if USERNAME and PASSWORD and captchasvc.active()[0]:
            log(f"auth lost — login lại qua {captchasvc.active()[0]}...")
            s.login(USERNAME, PASSWORD)
            save_session(s)
            return s.pass_gate()
        raise


def pick_mirror() -> int:
    if MIRROR:
        return MIRROR
    log("probing 20 mirrors for the fastest one...")
    ups = P.check_mirrors(range(1, 21))
    if not ups:
        raise SystemExit("no mirror responded — try again in a moment")
    for i, dt in ups[:5]:
        log(f"  new-portal{i}: {dt:.0f} ms")
    return ups[0][0]


def _print_rows(rows, title: str):
    log(f"--- {title} ({len(rows)}) ---")
    for r in rows:
        log(f"  {r['code']:9s} {r['name'][:34]:34s} {r['lop']:8s} "
            f"{r['tc']:>2s}TC  ĐK {r['enrolled']:>4s}/{r['capacity']:<5s} [{r['ctl']}] {r['table']}")


def next_alive_session(exclude: set[int]) -> PortalSession | None:
    """Mirror dự phòng có cookie còn sống (đã login trước đó)."""
    for m in cookiestore.known_mirrors():
        if m in exclude or not cookiestore.alive(m):
            continue
        log(f"chuyển sang mirror dự phòng new-portal{m} (cookie từ {cookiestore.source(m)})")
        return PortalSession(m, cookies=cookiestore.load(m), log=log)
    return None


# ---------------------------------------------------------------- commands
def cmd_mirrors(_a):
    ups = P.check_mirrors(range(1, 21))
    if not ups:
        log("NO mirror responded.")
        return
    for i, dt in ups:
        log(f"new-portal{i:2d}: {dt:6.0f} ms")
    log(f"=> fastest: new-portal{ups[0][0]}")


def cmd_login_manual(a):
    import browser_login
    mirrors = browser_login.parse_mirror_list(a.mirrors)
    if not (USERNAME and PASSWORD):
        raise SystemExit("Set USERNAME_SV / PASSWORD_SV in .env first.")
    browser_login.login_manual(mirrors, USERNAME, PASSWORD, force=a.force, log=log)


def cmd_sessions(_a):
    mirrors = cookiestore.known_mirrors()
    if not mirrors:
        log("chưa có cookie nào (sessions/ lẫn .env đều trống).")
        log("Chạy: python run.py login-manual   (hoặc dán cookie vào .env: PORTAL{N}_ASPXAUTH)")
        return
    log(f"kiểm tra cookie của {len(mirrors)} mirror (1 request mỗi cái)...")
    for m in mirrors:
        if cookiestore.alive(m):
            log(f"  new-portal{m:2d}: SỐNG ✅  (nguồn: {cookiestore.source(m)})")
        else:
            log(f"  new-portal{m:2d}: CHẾT ❌  (nguồn: {cookiestore.source(m)}) "
                f"— login lại: python run.py login-manual --mirrors {m} --force")


def login_all(force: bool = False):
    """Login tự động trên TẤT CẢ mirror đang sống — tạo kho cookie dự phòng cho race.
    Mirror đã có cookie còn sống thì bỏ qua (tiết kiệm tiền) trừ khi --force."""
    svc, key = captchasvc.active()
    if not (USERNAME and PASSWORD):
        raise SystemExit("Set USERNAME_SV / PASSWORD_SV in .env first.")
    if not svc:
        raise SystemExit("Cần key giải reCAPTCHA trong .env (ANTICAPTCHA_API_KEY của "
                         "anticaptcha.top hoặc TWOCAPTCHA_API_KEY). Không có key: "
                         "python run.py login-manual")
    bal = None
    if svc == "anticaptcha.top":
        bal = solver_anticaptcha.get_balance(key)
        log(f"số dư anticaptcha.top: {bal}đ")
    log("dò 20 mirror...")
    ups = P.check_mirrors(range(1, 21))
    if not ups:
        raise SystemExit("no mirror responded — try again in a moment")
    if len(ups) < 20:
        log(f"{len(ups)}/20 mirror đang phản hồi (còn lại đang nghẽn/chết — bỏ qua)")
    todo = [i for i, _ in ups if force or not cookiestore.alive(i)]
    skipped = [i for i, _ in ups if i not in todo]
    if skipped:
        log(f"bỏ qua {len(skipped)} mirror đã có cookie sống: "
            f"{','.join(map(str, skipped))} (dùng --force để làm lại)")
    if not todo:
        log("mọi mirror đang sống đều có cookie rồi — không cần login thêm.")
        return
    log(f"login lần lượt {len(todo)} mirror (~30-40 giây mỗi cái): "
        f"{','.join(map(str, todo))}")
    if bal is not None and bal < 33 * len(todo):
        log(f"⚠ số dư {bal}đ có thể không đủ (~{33 * len(todo)}đ cho {len(todo)} mirror)")
    ok, failed = [], []
    for i in todo:
        try:
            s = PortalSession(i, log=log)
            s.login(USERNAME, PASSWORD)
            save_session(s)
            ok.append(i)
        except Exception as e:  # noqa: BLE001
            log(f"new-portal{i}: LOGIN THẤT BẠI ({e})")
            failed.append(i)
        time.sleep(1)
    log(f"--- login-all xong: {len(ok)} OK, {len(failed)} thất bại "
        f"(trên {len(ups)} mirror sống) ---")
    if failed:
        log(f"thất bại: {','.join(map(str, failed))} — chạy lại lệnh này (chỉ làm lại "
            f"cái hỏng), hoặc login tay: python run.py login-manual --mirrors "
            f"{','.join(map(str, failed))}")


def cmd_login(a):
    if a.all:
        login_all(force=a.force)
        return
    m = a.mirror or pick_mirror()
    svc, key = captchasvc.active()
    if not svc:
        log("chưa có key giải captcha trong .env — mở browser cho bạn login tay (miễn phí)...")
        log("(muốn tự động 100%: điền ANTICAPTCHA_API_KEY của anticaptcha.top — VN, ~33đ/lần — "
            "hoặc TWOCAPTCHA_API_KEY; login nhiều mirror cùng lúc: python run.py login-manual)")
        import browser_login
        browser_login.login_manual([m], USERNAME, PASSWORD, log=log)
        return
    if svc == "anticaptcha.top":
        log(f"số dư anticaptcha.top: {solver_anticaptcha.get_balance(key)}đ")
    if not (USERNAME and PASSWORD):
        raise SystemExit("Set USERNAME_SV / PASSWORD_SV in .env first.")
    s = PortalSession(m, log=log)
    s.login(USERNAME, PASSWORD)
    save_session(s)


def cmd_cookie(a):
    m = a.mirror or pick_mirror()
    print(f"Paste cookies for new-portal{m} (browser F12 > Application > Cookies).")
    aspx = input(".ASPXAUTH: ").strip()
    sess = input("ASP.NET_SessionId: ").strip()
    s = PortalSession(m, cookies={".ASPXAUTH": aspx, "ASP.NET_SessionId": sess}, log=log)
    html = s.pass_gate()
    log(f"cookies work — course page loaded ({len(html)} bytes)")
    save_session(s)


def _ensure_mirror_cookie(m: int):
    """Bảo đảm mirror m có cookie sống: thiếu/thế thì login lại (tự động nếu có
    key dịch vụ, không thì mở browser login tay)."""
    if cookiestore.alive(m):
        return
    log(f"cookie new-portal{m} chưa có hoặc đã chết — cần login lại...")
    if USERNAME and PASSWORD and captchasvc.active()[0]:
        s = PortalSession(m, log=log)
        s.login(USERNAME, PASSWORD)
        save_session(s)
    else:
        import browser_login
        browser_login.login_manual([m], USERNAME, PASSWORD, log=log)


def _pick_open_mirror(exclude: set[int]) -> int:
    """Tầng 0 cho `open`: dò 20 mirror, trả về mirror nhanh nhất có cookie sống
    (trừ mấy mirror trong exclude); không có thì tự login trên mirror nhanh nhất
    (tốn ~33đ nếu qua dịch vụ). Trả về 0 = không chọn được."""
    skip = f" (trừ {sorted(exclude)})" if exclude else ""
    log(f"dò lại 20 mirror{skip}...")
    ups = [i for i, _ in P.check_mirrors(range(1, 21)) if i not in exclude]
    if not ups:
        log("không mirror nào khác phản hồi")
        return 0
    for i in ups:
        if cookiestore.alive(i):
            log(f"chọn new-portal{i} (cookie sống sẵn)")
            return i
    try:
        _ensure_mirror_cookie(ups[0])
        return ups[0]
    except Exception as e:  # noqa: BLE001
        log(f"login trên new-portal{ups[0]} thất bại ({e})")
        return 0


def cmd_open(a):
    """Mở trang ĐKHP trong browser để tự thao tác tay — tool lo chọn mirror
    nhanh nhất có cookie sống; cổng nghẽn đặc thì tự dò lại từ đầu và chuyển."""
    import browser_login

    def fallback(exclude: set[int]) -> int:
        try:
            return _pick_open_mirror(exclude)
        except Exception as e:  # noqa: BLE001
            log(f"dò lại thất bại ({e})")
            return 0

    if a.mirror:
        _ensure_mirror_cookie(a.mirror)
        m = a.mirror
    else:
        m = fallback(set())
        if not m:
            raise SystemExit("no mirror responded — try again in a moment")
    browser_login.open_dkhp(m, USERNAME, PASSWORD, fallback, log=log)


def cmd_status(a):
    s = load_session(a.mirror)
    html = ensure_ready(s)
    _print_rows(s.parse_registered(html), "Đã đăng ký")
    _print_rows(s.parse_open(html), "Lớp mở — có thể đăng ký")


def cmd_register(a):
    codes = [c.strip().upper() for c in a.codes.split(",") if c.strip()] or None
    s = load_session(a.mirror)
    html = ensure_ready(s)
    rows = s.parse_open(html)
    if not rows:
        log("no open classes right now.")
        return
    sel = [r for r in rows if not codes or r["code"] in codes] if codes else rows
    if codes:
        missing = set(codes) - {r["code"] for r in sel}
        if missing:
            log(f"NOT FOUND in open list: {sorted(missing)}")
    _print_rows(sel, "will register")
    if a.dry_run:
        log("dry-run, not submitting.")
        return
    ok, msg = s.register(html, [r["ctl"] for r in sel])
    log(f"server: {msg}")
    log("SUCCESS" if ok else "FAILED (see server message)")


def cmd_cancel(a):
    if not a.codes:
        raise SystemExit("--codes required, e.g. --codes MST10019")
    codes = [c.strip().upper() for c in a.codes.split(",") if c.strip()]
    s = load_session(a.mirror)
    html = ensure_ready(s)
    rows = [r for r in s.parse_registered(html) if r["code"] in codes]
    if not rows:
        log("none of those codes are currently registered.")
        return
    _print_rows(rows, "will cancel")
    ok, msg = s.cancel(html, [r["ctl"] for r in rows])
    log(f"server: {msg}")
    log("SUCCESS" if ok else "FAILED")


def cmd_race(a):
    codes = [c.strip().upper() for c in a.codes.split(",") if c.strip()] or None
    mirror = a.mirror or pick_mirror()
    s = load_session(mirror)
    log(f"RACE MODE on new-portal{s.mirror}: "
        + ("register ALL open classes" if not codes else f"targeting {codes}"))
    attempt = 0
    while True:
        attempt += 1
        try:
            html = ensure_ready(s)
            rows = s.parse_open(html)
            targets = [r for r in rows if not codes or r["code"] in codes]
            if not targets:
                if attempt % 20 == 1:
                    _print_rows(rows, f"[{attempt}] open classes so far")
                time.sleep(POLL + random.uniform(0, 0.4))
                continue
            log(f"[{attempt}] {len(targets)} target class(es) visible — FIRING")
            ok, msg = s.register(html, [r["ctl"] for r in targets])
            log(f"server: {msg}")
            if ok:
                html2 = ensure_ready(s)
                _print_rows(s.parse_registered(html2), "registered now")
                return
            if "đã đăng ký" in msg.lower():
                log("already registered — done")
                return
            time.sleep(POLL)
        except (P.LoginFailed, httpx.HTTPError, P.GateFailed) as e:
            log(f"mirror trouble ({type(e).__name__}: {e}) — tìm mirror dự phòng...")
            time.sleep(2)
            s = next_alive_session(exclude={s.mirror})
            if s:
                continue
            if USERNAME and PASSWORD and captchasvc.active()[0]:
                try:
                    log(f"không có cookie dự phòng — login lại qua {captchasvc.active()[0]}...")
                    m = pick_mirror()
                    s = PortalSession(m, log=log)
                    s.login(USERNAME, PASSWORD)
                    save_session(s)
                    continue
                except Exception as e2:  # noqa: BLE001
                    log(f"login lại thất bại ({e2})")
            time.sleep(10)


def main():
    p = argparse.ArgumentParser(description="HCMUS DKHP tool")
    sub = p.add_subparsers(dest="cmd", required=True)

    def with_mirror(sp):
        sp.add_argument("--mirror", type=int, default=0, help="portal mirror 1..20 (0=auto)")
        return sp

    with_mirror(sub.add_parser("mirrors"))
    sp = with_mirror(sub.add_parser("login"))
    sp.add_argument("--all", action="store_true",
                    help="login TẤT CẢ mirror đang sống — lưu cookie dự phòng cho race")
    sp.add_argument("--force", action="store_true",
                    help="(kèm --all) làm lại kể cả mirror đã có cookie còn sống")
    with_mirror(sub.add_parser("cookie"))
    with_mirror(sub.add_parser("status"))
    with_mirror(sub.add_parser("open"))

    sp = with_mirror(sub.add_parser("login-manual"))
    sp.add_argument("--mirrors", default="", help="vd: 4,11 hoặc 1-20; rỗng = tất cả 1..20")
    sp.add_argument("--force", action="store_true", help="login lại kể cả mirror đã có cookie")

    sub.add_parser("sessions")

    sp = with_mirror(sub.add_parser("register"))
    sp.add_argument("--codes", default="", help="comma-separated course codes; empty = ALL open")
    sp.add_argument("--dry-run", action="store_true")

    sp = with_mirror(sub.add_parser("cancel"))
    sp.add_argument("--codes", default="")

    sp = with_mirror(sub.add_parser("race"))
    sp.add_argument("--codes", default="")

    args = p.parse_args()
    dict(mirrors=cmd_mirrors, login=cmd_login, cookie=cmd_cookie, status=cmd_status,
         open=cmd_open, login_manual=cmd_login_manual, sessions=cmd_sessions,
         register=cmd_register, cancel=cmd_cancel, race=cmd_race)[args.cmd](args)


if __name__ == "__main__":
    main()
