"""CLI tool: HCMUS course registration (new-portalX.hcmus.edu.vn).

Commands:
  python run.py mirrors                 check which of the 20 mirrors are up
  python run.py login [--mirror N]      auto-login via 2captcha, save cookies
  python run.py login-manual            login tay qua browser cho mọi mirror
                                       [--mirrors 4,11|1-20] [--force]
  python run.py cookie [--mirror N]     paste cookies from your browser instead
  python run.py sessions                trạng thái cookie đã lưu (sống/chết)
  python run.py status [--mirror N]     show registered + open classes
  python run.py register [--codes A,B] [--dry-run]   register ALL open classes (or subset)
  python run.py cancel --codes A,B      cancel registrations
  python run.py race [--codes A,B]      loop until classes open, register instantly

Config lives in .env next to this file (see .env.example).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

import httpx
from dotenv import load_dotenv

import portal as P
from portal import PortalSession

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

USERNAME = os.getenv("USERNAME_SV", "")
PASSWORD = os.getenv("PASSWORD_SV", "")
API_KEY = os.getenv("TWOCAPTCHA_API_KEY", "")
MIRROR = int(os.getenv("MIRROR", "0") or 0)  # 0 = auto (fastest alive)
POLL = float(os.getenv("POLL_INTERVAL", "1.0"))
SESSIONS = ROOT / "sessions"


def log(msg: str):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def load_session(mirror: int = 0) -> PortalSession:
    m = mirror or MIRROR
    if not m:
        raise SystemExit("No mirror selected. Run `python run.py mirrors`, set MIRROR in .env, "
                         "or pass --mirror N.")
    cookies = None
    f = SESSIONS / f"portal{m}.json"
    if f.exists():
        cookies = json.loads(f.read_text())
        log(f"loaded saved cookies for new-portal{m}")
    return PortalSession(m, cookies=cookies, log=log)


def save_session(s: PortalSession):
    SESSIONS.mkdir(exist_ok=True)
    (SESSIONS / f"portal{s.mirror}.json").write_text(json.dumps(s.cookie_dict()))
    log(f"cookies saved for new-portal{s.mirror}")


def ensure_ready(s: PortalSession) -> str:
    """Pass the captcha gate; auto re-login through 2captcha if auth expired."""
    try:
        return s.pass_gate(api_key=API_KEY or None)
    except P.LoginFailed:
        if USERNAME and PASSWORD and API_KEY:
            log("auth lost — re-login via 2captcha...")
            s.login(USERNAME, PASSWORD, API_KEY)
            save_session(s)
            return s.pass_gate(api_key=API_KEY)
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
    import browser_login
    if not SESSIONS.exists():
        return None
    for f in sorted(SESSIONS.glob("portal*.json")):
        try:
            m = int(f.stem.replace("portal", ""))
        except ValueError:
            continue
        if m in exclude or not browser_login.session_alive(m):
            continue
        log(f"chuyển sang mirror dự phòng new-portal{m} (cookie sẵn)")
        return PortalSession(m, cookies=json.loads(f.read_text()), log=log)
    return None


# ---------------------------------------------------------------- commands


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
    import browser_login
    if not SESSIONS.exists() or not list(SESSIONS.glob("portal*.json")):
        log("chưa có cookie nào. Chạy: python run.py login-manual")
        return
    log("kiểm tra cookie đã lưu (gọi 1 request mỗi mirror)...")
    for f in sorted(SESSIONS.glob("portal*.json"),
                    key=lambda p: int(p.stem.replace("portal", ""))):
        m = int(f.stem.replace("portal", ""))
        alive = browser_login.session_alive(m)
        log(f"  new-portal{m:2d}: {'SỐNG ✅' if alive else 'CHẾT ❌ (login lại: python run.py login-manual --mirrors %d --force)' % m}")


def cmd_login(a):
    m = a.mirror or pick_mirror()
    if not API_KEY:
        log("chưa có TWOCAPTCHA_API_KEY trong .env — mở browser cho bạn login tay (miễn phí)...")
        log("(muốn tự động 100% thì nạp key 2captcha; muốn login nhiều mirror cùng lúc: python run.py login-manual)")
        import browser_login
        browser_login.login_manual([m], USERNAME, PASSWORD, log=log)
        return
    if not (USERNAME and PASSWORD):
        raise SystemExit("Set USERNAME_SV / PASSWORD_SV in .env first.")
    s = PortalSession(m, log=log)
    s.login(USERNAME, PASSWORD, API_KEY)
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
            if USERNAME and PASSWORD and API_KEY:
                try:
                    log("không có cookie dự phòng — login lại qua 2captcha...")
                    m = pick_mirror()
                    s = PortalSession(m, log=log)
                    s.login(USERNAME, PASSWORD, API_KEY)
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
    with_mirror(sub.add_parser("login"))
    with_mirror(sub.add_parser("cookie"))
    with_mirror(sub.add_parser("status"))

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
         login_manual=cmd_login_manual, sessions=cmd_sessions,
         register=cmd_register, cancel=cmd_cancel, race=cmd_race)[args.cmd](args)


if __name__ == "__main__":
    main()
