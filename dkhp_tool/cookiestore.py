"""Nơi lưu/tìm cookie cho các mirror.

Thứ tự ưu tiên khi lấy cookie cho mirror N:
  1. sessions/portal{N}.json  (tool tự ghi khi login thành công — luôn mới nhất)
  2. biến .env  PORTAL{N}_ASPXAUTH / PORTAL{N}_SESSIONID  (dán tay từ browser)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from portal import PortalSession

SESSIONS = Path(__file__).parent / "sessions"


def file_cookie(mirror: int) -> dict[str, str] | None:
    f = SESSIONS / f"portal{mirror}.json"
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text())
        return data if data.get(".ASPXAUTH") else None
    except (ValueError, OSError):
        return None


def env_cookie(mirror: int) -> dict[str, str] | None:
    aspx = os.getenv(f"PORTAL{mirror}_ASPXAUTH", "").strip()
    if not aspx:
        return None
    return {
        ".ASPXAUTH": aspx,
        "ASP.NET_SessionId": os.getenv(f"PORTAL{mirror}_SESSIONID", "").strip(),
    }


def load(mirror: int) -> dict[str, str] | None:
    return file_cookie(mirror) or env_cookie(mirror)


def save(mirror: int, cookies: dict[str, str]) -> None:
    SESSIONS.mkdir(exist_ok=True)
    (SESSIONS / f"portal{mirror}.json").write_text(json.dumps(cookies))


def source(mirror: int) -> str:
    if file_cookie(mirror):
        return "sessions/*.json"
    if env_cookie(mirror):
        return ".env"
    return "-"


def known_mirrors() -> list[int]:
    """Các mirror có cookie từ nguồn bất kỳ (file hoặc .env)."""
    out = set()
    if SESSIONS.exists():
        for f in SESSIONS.glob("portal*.json"):
            try:
                out.add(int(f.stem.replace("portal", "")))
            except ValueError:
                pass
    for key, val in os.environ.items():
        if key.startswith("PORTAL") and key.endswith("_ASPXAUTH") and val.strip():
            try:
                out.add(int(key[6:-len("_ASPXAUTH")]))
            except ValueError:
                pass
    return sorted(out)


def alive(mirror: int) -> bool:
    """Cookie của mirror này còn dùng được không? (bị đá về Login = chết)."""
    cookies = load(mirror)
    if not cookies or not cookies.get(".ASPXAUTH"):
        return False
    try:
        s = PortalSession(mirror, cookies=cookies, timeout=15)
        r = s.client.get(s.base + "/DangKyHocPhan.aspx")
        # cookie chết => bị redirect về /Login.aspx?ReturnUrl=...
        return r.status_code == 200 and "/Login.aspx" not in str(r.url)
    except Exception:  # noqa: BLE001
        return False
