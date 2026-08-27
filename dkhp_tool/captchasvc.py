"""Chọn dịch vụ giải captcha có khóa trong .env.

Ưu tiên anticaptcha.top (Việt Nam, ~30đ/lần, thanh toán nội địa),
2captcha.com chỉ dùng khi không có khóa anticaptcha.

Đọc biến môi trường lúc GỌI (không phải lúc import) để kịp nhận giá trị
từ load_dotenv() của run.py.
"""
from __future__ import annotations

import os

import solver_2captcha
import solver_anticaptcha


def active() -> tuple[str | None, str]:
    """(tên dịch vụ, api key); (None, "") nếu chưa cấu hình khóa nào."""
    key = os.getenv("ANTICAPTCHA_API_KEY", "").strip()
    if key:
        return "anticaptcha.top", key
    key = os.getenv("TWOCAPTCHA_API_KEY", "").strip()
    if key:
        return "2captcha.com", key
    return None, ""


def solve_recaptcha_v2(sitekey: str, page_url: str, log=print) -> str | None:
    name, key = active()
    if not key:
        return None
    solver = solver_anticaptcha if name == "anticaptcha.top" else solver_2captcha
    return solver.solve_recaptcha_v2(key, sitekey, page_url,
                                     log=lambda m: log(f"[{name}] {m}"))


def solve_image_captcha(image_bytes: bytes, log=print) -> str | None:
    name, key = active()
    if not key:
        return None
    solver = solver_anticaptcha if name == "anticaptcha.top" else solver_2captcha
    return solver.solve_image_captcha(key, image_bytes,
                                      log=lambda m: log(f"[{name}] {m}"))
