"""2captcha client: Google reCAPTCHA v2 (login) + image captcha fallback."""
from __future__ import annotations

import time
import urllib.parse
import urllib.request

API_IN = "https://2captcha.com/in.php"
API_RES = "https://2captcha.com/res.php"


def _get(url: str) -> str:
    return urllib.request.urlopen(urllib.request.Request(url), timeout=30).read().decode()


def solve_recaptcha_v2(api_key: str, sitekey: str, page_url: str,
                       timeout: int = 180, poll: float = 5.0,
                       log=lambda m: None) -> str:
    """Submit a reCAPTCHA v2 task, poll until solved, return g-recaptcha-response."""
    data = urllib.parse.urlencode({
        "key": api_key,
        "method": "userrecaptcha",
        "googlekey": sitekey,
        "pageurl": page_url,
    }).encode()
    resp = urllib.request.urlopen(urllib.request.Request(API_IN, data=data), timeout=30).read().decode()
    if "|" not in resp:
        raise RuntimeError(f"2captcha in.php: {resp}")
    status, task_id = resp.split("|", 1)
    if status != "OK":
        raise RuntimeError(f"2captcha in.php rejected: {resp}")
    log(f"2captcha task {task_id} submitted, waiting for workers...")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(poll)
        r = _get(f"{API_RES}?key={api_key}&action=get&id={task_id}")
        if "|" in r:
            status, payload = r.split("|", 1)
            if status == "OK":
                return payload
            if payload == "CAPCHA_NOT_READY":
                continue
        raise RuntimeError(f"2captcha res.php: {r}")
    raise RuntimeError("2captcha timeout")


def solve_image_captcha(api_key: str, image_bytes: bytes,
                        timeout: int = 120, poll: float = 5.0,
                        log=lambda m: None) -> str:
    """Fallback: send the 6-digit image captcha to 2captcha workers."""
    import base64
    data = urllib.parse.urlencode({
        "key": api_key,
        "method": "base64",
        "json": "0",
        "body": base64.b64encode(image_bytes).decode(),
    }).encode()
    resp = urllib.request.urlopen(urllib.request.Request(API_IN, data=data), timeout=30).read().decode()
    if "|" not in resp:
        raise RuntimeError(f"2captcha in.php: {resp}")
    status, task_id = resp.split("|", 1)
    if status != "OK":
        raise RuntimeError(f"2captcha in.php rejected: {resp}")
    log(f"2captcha image task {task_id} submitted...")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(poll)
        r = _get(f"{API_RES}?key={api_key}&action=get&id={task_id}")
        if "|" in r:
            status, payload = r.split("|", 1)
            if status == "OK":
                return payload
            if payload == "CAPCHA_NOT_READY":
                continue
        raise RuntimeError(f"2captcha res.php: {r}")
    raise RuntimeError("2captcha timeout")
