"""Login tay qua browser thật (Playwright) cho nhiều mirror cùng lúc.

Tool mở cửa sổ Chromium, tự điền tài khoản/mật khẩu cho từng mirror chưa có
cookie; bạn chỉ việc tick reCAPTCHA + bấm "Đăng nhập". Tool tự phát hiện
cookie .ASPXAUTH xuất hiện, lưu + verify, rồi chuyển mirror kế tiếp.
"""
from __future__ import annotations

import random
import time

import cookiestore

TIMEOUT_PER_MIRROR = 300  # giây


def parse_mirror_list(spec: str) -> list[int]:
    """'4,11' | '1-20' | '' -> list mirror numbers."""
    spec = (spec or "").strip()
    if not spec:
        return list(range(1, 21))
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return [m for m in out if 1 <= m <= 20]


def session_alive(mirror: int) -> bool:
    """Cookie của mirror (file sessions/ hoặc .env) còn dùng được không?"""
    return cookiestore.alive(mirror)


def open_dkhp(mirror: int, username: str = "", password: str = "",
              pick_fallback=None, log=print):
    """Mở trang ĐKHP của mirror trong Chromium (cookie gắn sẵn) — bạn tự gõ
    mã 6 số, tự tick môn và bấm đăng ký.

    Ngày đông người: tự F5 (~1 giây/lần) tới khi trang lên thật; phiên chết
    giữa chừng thì tự login lại qua dịch vụ giải captcha rồi mở lại trang;
    mirror nghẽn đặc (F5 hoài không lên) thì gọi pick_fallback() để dò lại
    20 mirror từ tầng 0 và chuyển cổng. Cookie được lưu liên tục trong lúc
    cửa sổ mở."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "Cần cài Playwright trước:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )
    cookies = cookiestore.load(mirror)
    if not cookies or not cookies.get(".ASPXAUTH"):
        raise SystemExit(f"chưa có cookie cho new-portal{mirror} — chạy trước: "
                         f"python run.py login --mirror {mirror}")
    cur_m = mirror

    def base_of(m: int) -> str:
        return f"https://new-portal{m}.hcmus.edu.vn"

    def gate_of(m: int) -> str:
        return base_of(m) + "/DangKyHocPhan.aspx"

    def inject(m: int):
        cc = cookiestore.load(m)
        ctx.add_cookies([{"name": k, "value": v, "domain": base_of(m)[8:], "path": "/"}
                         for k, v in cc.items()])

    def relogin(m: int) -> bool:
        """Login lại ngoài browser (httpx + dịch vụ giải captcha, ~33đ/lần)."""
        import captchasvc
        import portal as P
        svc, _key = captchasvc.active()
        if not (username and password and svc):
            return False
        try:
            s = P.PortalSession(m, log=log)
            s.login(username, password)
            cookiestore.save(m, s.cookie_dict())
            return True
        except Exception as e:  # noqa: BLE001
            log(f"[portal{m}] login lại thất bại ({e})")
            return False

    def switch_mirror() -> bool:
        """Cổng hiện tại nghẽn đặc — dò lại từ tầng 0, chuyển cổng nếu được."""
        nonlocal cur_m
        if not pick_fallback:
            return False
        nxt = pick_fallback({cur_m})
        if not nxt or nxt == cur_m:
            return False
        log(f"[portal{cur_m}] nghẽn quá — CHUYỂN CỔNG sang new-portal{nxt}")
        cur_m = nxt
        ctx.clear_cookies()
        inject(cur_m)
        return True

    def page_broken(html: str) -> bool:
        """Trang lỗi/nghẽn: rỗng, ngắn bất thường, hoặc error page của server."""
        h = html[:4000].lower()
        return (len(html) < 500 or "service unavailable" in h
                or "bad gateway" in h or "gateway timeout" in h
                or "runtime error" in h)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context()
        inject(cur_m)
        page = ctx.new_page()
        try:
            # ---- phase 1: đánh tới khi trang ĐKHP lên thật (tự F5 ~1s/lần) ----
            attempt, up, fail_streak = 0, False, 0
            while browser.is_connected() and not up:
                attempt += 1
                try:
                    page.goto(gate_of(cur_m), timeout=15000)
                except Exception:  # noqa: BLE001 — nghẽn/timeout: vòng sau đánh lại
                    pass
                try:
                    url, html = page.url, page.content()
                except Exception:  # noqa: BLE001
                    time.sleep(1)
                    continue
                if "/Login.aspx" in url:
                    fail_streak = 0
                    log(f"[portal{cur_m}] [{attempt}] phiên chết — login lại...")
                    if relogin(cur_m):
                        ctx.clear_cookies()
                        inject(cur_m)
                    else:
                        log(f"[portal{cur_m}] tự login không được — bạn login tay "
                            f"trong cửa sổ, tool tự phát hiện và chuyển tiếp")
                        deadline = time.time() + 600
                        while browser.is_connected() and time.time() < deadline:
                            if any(c["name"] == ".ASPXAUTH"
                                   for c in ctx.cookies(base_of(cur_m))):
                                cookiestore.save(cur_m, {c["name"]: c["value"]
                                                         for c in ctx.cookies(base_of(cur_m))})
                                break
                            page.wait_for_timeout(1000)
                elif not page_broken(html):
                    up = True
                    log(f"[portal{cur_m}] [{attempt}] TRANG LÊN RỒI — gõ mã 6 số "
                        f"và thao tác nhé. Đóng cửa sổ khi xong.")
                else:
                    fail_streak += 1
                    if fail_streak >= 12:  # ~15-25 giây không lên: cổng nghẽn đặc
                        if switch_mirror():
                            fail_streak = 0
                            continue
                        fail_streak = 0  # hết cổng tốt hơn — ở lại F5 tiếp
                    if attempt % 10 == 1:
                        log(f"[portal{cur_m}] [{attempt}] server chưa lên — tự F5 tiếp...")
                    page.wait_for_timeout(1000 + random.randint(0, 400))
            # ---- phase 2: canh cửa sổ — lưu cookie + tự cứu khi bị đá về login ----
            last, warned = "", False
            need_nav = False
            last_relogin = 0.0
            while browser.is_connected():
                try:
                    cur = {c["name"]: c["value"] for c in ctx.cookies(base_of(cur_m))}
                    if cur.get(".ASPXAUTH") and cur != last:
                        cookiestore.save(cur_m, cur)
                        last = cur
                    if "/Login.aspx" in page.url:
                        if need_nav:  # đã login lại — chỉ cần mở lại trang (free)
                            try:
                                page.goto(gate_of(cur_m), timeout=20000)
                                need_nav = False
                            except Exception:  # noqa: BLE001
                                pass  # nghẽn: vòng sau thử lại, không tốn tiền
                        elif time.time() - last_relogin > 30:
                            last_relogin = time.time()
                            if relogin(cur_m):
                                ctx.clear_cookies()
                                inject(cur_m)
                                need_nav = True
                            elif not warned:
                                warned = True
                                log(f"[portal{cur_m}] phiên chết và không tự login "
                                    f"được — bạn login tay trong cửa sổ nhé")
                    page.wait_for_timeout(1500)
                except Exception:  # noqa: BLE001 — cửa sổ vừa bị đóng giữa chừng
                    break
        except KeyboardInterrupt:
            log("\nđóng theo Ctrl+C")
        finally:
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass
    log(f"[portal{cur_m}] cửa sổ đã đóng — cookie mới nhất đã lưu.")


def login_manual(mirrors: list[int], username: str, password: str,
                 force: bool = False, log=print):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "Cần cài Playwright trước:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )

    todo = [m for m in mirrors if force or not session_alive(m)]
    already = [m for m in mirrors if m not in todo]
    if already:
        log(f"bỏ qua (cookie còn sống): {already}  — dùng --force nếu muốn làm lại")
    if not todo:
        log("không mirror nào cần login.")
        return
    log(f"cần login tay: {todo}")
    log("mỗi mirror: tick reCAPTCHA + bấm Đăng nhập. Ctrl+C để dừng.\n")

    done: list[int] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            for m in todo:
                base = f"https://new-portal{m}.hcmus.edu.vn"
                try:
                    page.goto(base + "/Login.aspx", timeout=30000)
                    page.fill('input[name="ctl00$ContentPlaceHolder1$txtUsername"]', username, timeout=8000)
                    page.fill('input[name="ctl00$ContentPlaceHolder1$txtPassword"]', password, timeout=8000)
                except Exception as e:  # noqa: BLE001
                    log(f"[portal{m}] trang lạ/không điền được ({type(e).__name__}) — tự điền tay nhé")

                log(f"[portal{m}] chờ bạn tick reCAPTCHA + Đăng nhập...")
                got = None
                deadline = time.time() + TIMEOUT_PER_MIRROR
                while time.time() < deadline:
                    for c in ctx.cookies(base):
                        if c["name"] == ".ASPXAUTH":
                            got = {cc["name"]: cc["value"] for cc in ctx.cookies(base)}
                            break
                    if got:
                        break
                    page.wait_for_timeout(800)

                if not got:
                    log(f"[portal{m}] HẾT GIỜ (5 phút) — bỏ qua, quay lại sau bằng --mirrors {m}")
                    continue

                SESSIONS_SAVE = {
                    ".ASPXAUTH": got.get(".ASPXAUTH", ""),
                    "ASP.NET_SessionId": got.get("ASP.NET_SessionId", ""),
                }
                cookiestore.save(m, SESSIONS_SAVE)
                if session_alive(m):
                    log(f"[portal{m}] ✅ cookie đã lưu + verify OK")
                    done.append(m)
                else:
                    log(f"[portal{m}] ⚠️ cookie lưu nhưng verify FAIL — chạy lại: --mirrors {m} --force")
                ctx.clear_cookies()  # sạch sẽ cho mirror kế tiếp
        except KeyboardInterrupt:
            log("\ndừng theo Ctrl+C")
        finally:
            browser.close()
    log(f"\nxong: {done if done else 'không mirror nào'} "
        f"(cookie nằm trong sessions/portal*.json)")
