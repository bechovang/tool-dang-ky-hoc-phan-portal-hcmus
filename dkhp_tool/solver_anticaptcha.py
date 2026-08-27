"""anticaptcha.top client — dịch vụ giải captcha Việt Nam, thanh toán nội địa.

Khác 2captcha: KHÔNG cần poll 2 bước. Một POST duy nhất, server giữ request
tới khi giải xong rồi trả luôn kết quả trong response.
  - ReCaptcha V2: {"apikey", "type": 11, "googlesitekey", "pageurl"} -> captcha=token
  - Ảnh -> text : {"apikey", "type": 9,  "img": base64}                -> captcha=text
Docs: https://docs.anticaptcha.top (GET /api/getbalance?apikey= để xem số dư)
"""
from __future__ import annotations

import base64
import json
import urllib.request

API = "https://anticaptcha.top/api/captcha"
BALANCE = "https://anticaptcha.top/api/getbalance"

# Cloudflare của họ chặn User-Agent mặc định của Python — phải giả làm browser
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def _post(payload: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        API, data=json.dumps(payload).encode(), headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get_balance(api_key: str) -> float | None:
    try:
        req = urllib.request.Request(f"{BALANCE}?apikey={api_key}", headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode())
        return float(d["balance"]) if d.get("success") else None
    except Exception:  # noqa: BLE001
        return None


def solve_recaptcha_v2(api_key: str, sitekey: str, page_url: str,
                       timeout: int = 180, log=lambda m: None) -> str | None:
    log("đã gửi reCAPTCHA v2 (loại 11), chờ anticaptcha.top giải...")
    d = _post({"apikey": api_key, "type": 11,
               "googlesitekey": sitekey, "pageurl": page_url}, timeout)
    if d.get("success") and d.get("captcha"):
        log("đã có token reCAPTCHA")
        return d["captcha"]
    log(f"thất bại: {d.get('message') or 'không rõ lý do'}")
    return None


def solve_image_captcha(api_key: str, image_bytes: bytes,
                        timeout: int = 120, log=lambda m: None) -> str | None:
    d = _post({"apikey": api_key, "type": 9,
               "img": base64.b64encode(image_bytes).decode()}, timeout)
    if d.get("success") and d.get("captcha"):
        return str(d["captcha"]).strip()
    return None
