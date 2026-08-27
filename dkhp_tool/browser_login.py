"""Login tay qua browser thật (Playwright) cho nhiều mirror cùng lúc.

Tool mở cửa sổ Chromium, tự điền tài khoản/mật khẩu cho từng mirror chưa có
cookie; bạn chỉ việc tick reCAPTCHA + bấm "Đăng nhập". Tool tự phát hiện
cookie .ASPXAUTH xuất hiện, lưu + verify, rồi chuyển mirror kế tiếp.
"""
from __future__ import annotations

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
