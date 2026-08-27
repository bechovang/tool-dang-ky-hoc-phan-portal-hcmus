"""HCMUS new-portal course-registration client (ASP.NET WebForms).

Handles: login (reCAPTCHA v2 qua captchasvc — anticaptcha.top hoặc 2captcha),
the 6-digit captcha gate on DangKyHocPhan.aspx (local segmentation OCR,
service fallback), parsing the registered/open-class tables, and the
register/cancel postbacks.

Reverse-engineered from new-portal4.hcmus.edu.vn, verified live 2026-08-27.
"""
from __future__ import annotations

import re
import time

import httpx

import captchasvc
from captcha_solver import solve as solve_captcha_ocr


class GateFailed(Exception):
    pass


class LoginFailed(Exception):
    pass


def _hidden_fields(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*name="([^"]*)"[^>]*value="([^"]*)"', html, re.I):
        out[m.group(1)] = m.group(2)
    for m in re.finditer(r'<input[^>]*name="([^"]*)"[^>]*type="hidden"[^>]*value="([^"]*)"', html, re.I):
        out[m.group(1)] = m.group(2)
    return out


def _cells(row_html: str) -> list[str]:
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
            for c in re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)]


def _table_id_of(html: str, pos: int) -> str:
    """Table id that contains byte-position pos."""
    best = ""
    for m in re.finditer(r'<table[^>]*id="([^"]+)"', html):
        if m.start() < pos:
            best = m.group(1)
    return best


class PortalSession:
    def __init__(self, mirror: int, cookies: dict[str, str] | None = None,
                 timeout: float = 30.0, log=print):
        self.base = f"https://new-portal{mirror}.hcmus.edu.vn"
        self.mirror = mirror
        self.log = log
        self.client = httpx.Client(
            verify=False, timeout=timeout, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        if cookies:
            self.client.cookies.update(cookies)

    # ------------------------------------------------------------- low level
    def _get(self, path: str) -> httpx.Response:
        r = self.client.get(self.base + path)
        return r

    def _post_form(self, path: str, fields: dict[str, str]) -> httpx.Response:
        return self.client.post(self.base + path, data=fields,
                                headers={"Referer": self.base + path})

    def authed(self) -> bool:
        return any(c.name == ".ASPXAUTH" for c in self.client.cookies.jar)

    def cookie_dict(self) -> dict[str, str]:
        return {c.name: c.value for c in self.client.cookies.jar}

    # ----------------------------------------------------------------- login
    def login(self, username: str, password: str):
        """Login qua reCAPTCHA v2. Cần key dịch vụ giải captcha trong .env
        (ANTICAPTCHA_API_KEY hoặc TWOCAPTCHA_API_KEY — xem captchasvc.py)."""
        name, _key = captchasvc.active()
        if not name:
            raise LoginFailed(
                "Cần key giải reCAPTCHA trong .env: ANTICAPTCHA_API_KEY (anticaptcha.top, "
                "VN, ~33đ/lần) hoặc TWOCAPTCHA_API_KEY — hoặc dùng `run.py login-manual` "
                "để login tay qua browser (miễn phí)."
            )
        r = self._get("/Login.aspx")
        html = r.text
        m = re.search(r'data-sitekey="([^"]+)"', html)
        if not m:
            raise LoginFailed("reCAPTCHA sitekey not found on login page")
        sitekey = m.group(1)
        self.log(f"[login] giải reCAPTCHA v2 qua {name} (sitekey {sitekey[:12]}...)...")
        token = captchasvc.solve_recaptcha_v2(sitekey, self.base + "/Login.aspx",
                                              log=lambda m: self.log(m))
        if not token:
            raise LoginFailed(f"{name} không giải được reCAPTCHA")
        fields = _hidden_fields(html)
        fields.update({
            "ctl00$ContentPlaceHolder1$txtUsername": username,
            "ctl00$ContentPlaceHolder1$txtPassword": password,
            "g-recaptcha-response": token,
            "ctl00$ContentPlaceHolder1$btnLogin": "Đăng nhập",
        })
        r = self._post_form("/Login.aspx", fields)
        if not self.authed():
            err = re.search(r"Captcha[^<.]*|không đúng[^<.]*", r.text, re.I)
            raise LoginFailed("login rejected" + (f": {err.group(0)}" if err else ""))
        self.log(f"[login] OK on new-portal{self.mirror} — cookies captured")

    # ------------------------------------------------------------- captcha gate
    def pass_gate(self, max_tries: int = 12) -> str:
        """Ensure we are past the 6-digit captcha gate; return the course page HTML."""
        for i in range(1, max_tries + 1):
            r = self._get("/DangKyHocPhan.aspx")
            if "btnLogin" in r.text[-4000:] and not self.authed():
                raise LoginFailed("auth lost — re-login needed")
            if "txtCaptcha" not in r.text or "btnVaoDKHP" not in r.text:
                return r.text  # already past the gate

            img = self.client.get(self.base + "/Handlers/Captcha.ashx").content
            code = solve_captcha_ocr(img)
            if not code and captchasvc.active()[0]:
                try:
                    code = captchasvc.solve_image_captcha(img, log=lambda m: self.log(m))
                except Exception as e:  # noqa: BLE001
                    self.log(f"[gate {i}] image-captcha fallback failed: {e}")
            if not code:
                self.log(f"[gate {i}] local OCR no candidate, refetch")
                continue

            fields = _hidden_fields(r.text)
            fields["ctl00$ContentPlaceHolder1$txtCaptcha"] = code
            fields["ctl00$ContentPlaceHolder1$btnVaoDKHP"] = "Vào đăng ký học phần"
            r2 = self._post_form("/DangKyHocPhan.aspx", fields)
            if "btnVaoDKHP" in r2.text and "txtCaptcha" in r2.text:
                self.log(f"[gate {i}] wrong captcha ({code}), retry")
                continue
            return r2.text
        raise GateFailed(f"captcha gate not passed after {max_tries} tries")

    # ---------------------------------------------------------------- parsing
    def parse_registered(self, html: str) -> list[dict]:
        out = []
        for m in re.finditer(r"<tr[^>]*>(?:(?!</tr>).)*?rptLopDaDK\$ctl\d+\$cbHuyDK(?:(?!</tr>).)*?</tr>", html, re.S):
            row = m.group(0)
            ctl = re.search(r"rptLopDaDK\$(ctl\d+)\$", row).group(1)
            lopid = re.search(r'hdfLopMoID" value="(\d+)"', row)
            c = [x for x in _cells(row) if x]
            out.append({
                "ctl": ctl, "lopmo_id": lopid.group(1) if lopid else "",
                "code": c[0] if len(c) > 0 else "", "name": c[1] if len(c) > 1 else "",
                "lop": c[2] if len(c) > 2 else "", "tc": c[3] if len(c) > 3 else "",
                "capacity": c[4] if len(c) > 4 else "", "enrolled": c[5] if len(c) > 5 else "",
                "table": _table_id_of(html, m.start()),
                "raw_cells": c,
            })
        return out

    def parse_open(self, html: str) -> list[dict]:
        """Rows still available to register (checkbox cbDK present)."""
        out = []
        for m in re.finditer(r"<tr[^>]*>(?:(?!</tr>).)*?rptLopMoDKHP\$ctl\d+\$cbDK(?:(?!</tr>).)*?</tr>", html, re.S):
            row = m.group(0)
            ctl = re.search(r"rptLopMoDKHP\$(ctl\d+)\$", row).group(1)
            lopid = re.search(r'hdfLopMoID" value="(\d+)"', row)
            c = [x for x in _cells(row) if x]
            out.append({
                "ctl": ctl, "lopmo_id": lopid.group(1) if lopid else "",
                "code": c[0] if len(c) > 0 else "", "name": c[1] if len(c) > 1 else "",
                "lop": c[2] if len(c) > 2 else "", "tc": c[3] if len(c) > 3 else "",
                "capacity": c[4] if len(c) > 4 else "", "enrolled": c[5] if len(c) > 5 else "",
                "table": _table_id_of(html, m.start()),
                "raw_cells": c,
            })
        return out

    # ----------------------------------------------------------------- actions
    def register(self, html: str, ctls: list[str]) -> tuple[bool, str]:
        """Tick the given rptLopMoDKHP row checkboxes and click btnDangKy."""
        if not ctls:
            return False, "no rows selected"
        fields = _hidden_fields(html)
        for ctl in ctls:
            fields[f"ctl00$ContentPlaceHolder1$ViewThongTinDangKy1$rptLopMoDKHP${ctl}$cbDK"] = "on"
        fields["ctl00$ContentPlaceHolder1$ViewThongTinDangKy1$btnDangKy"] = "Đăng Ký"
        r = self._post_form("/DangKyHocPhan.aspx", fields)
        msg = self._extract_msg(r.text)
        ok = "thành công" in msg
        return ok, msg or "(no message)"

    def cancel(self, html: str, ctls: list[str]) -> tuple[bool, str]:
        if not ctls:
            return False, "no rows selected"
        fields = _hidden_fields(html)
        for ctl in ctls:
            fields[f"ctl00$ContentPlaceHolder1$ViewThongTinDangKy1$rptLopDaDK${ctl}$cbHuyDK"] = "on"
        fields["ctl00$ContentPlaceHolder1$ViewThongTinDangKy1$btnDelete"] = "Hủy Đăng Ký"
        r = self._post_form("/DangKyHocPhan.aspx", fields)
        msg = self._extract_msg(r.text)
        ok = "thành công" in msg
        return ok, msg or "(no message)"

    @staticmethod
    def _extract_msg(html: str) -> str:
        m = re.search(r'id="[^"]*divMsg"[^>]*>\s*([^<]+)', html)
        if m and m.group(1).strip():
            return m.group(1).strip()
        # fallback: any "thành công" line
        m = re.search(r"([^<>]{0,80}(?:thành công|không thành công|lỗi)[^<>]{0,80})", html, re.I)
        return m.group(1).strip() if m else ""


# ------------------------------------------------------------ mirror checking
def check_mirrors(mirrors: range | list[int], timeout: float = 8.0) -> list[tuple[int, float]]:
    """Ping each mirror, return [(mirror, latency_ms)] sorted fastest-first."""
    results = []
    for i in mirrors:
        t0 = time.time()
        try:
            r = httpx.get(f"https://new-portal{i}.hcmus.edu.vn/Login.aspx",
                          verify=False, timeout=timeout, follow_redirects=True)
            dt = (time.time() - t0) * 1000
            if r.status_code == 200:
                results.append((i, dt))
        except Exception:  # noqa: BLE001
            pass
    results.sort(key=lambda x: x[1])
    return results
