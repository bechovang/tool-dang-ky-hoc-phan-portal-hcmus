# Tool Đăng Ký Học Phần — Portal HCMUS

Tool tự động đăng ký học phần trên hệ `new-portalX.hcmus.edu.vn`
(ĐH Khoa học Tự nhiên, TP.HCM). Viết bằng Python, chạy HTTP thuần — không
cần mở browser khi chạy, vượt được cả 2 lớp captcha của hệ thống.

Đã test trực tiếp trên hệ thật (27/08/2026): vượt cổng captcha 6 số, hủy đăng ký,
đăng ký lại thành công.

## Tính năng

- **Race mode**: chờ đến giờ mở đăng ký → tự tick + submit ngay khi môn xuất hiện
- Tự vượt **captcha 6 số** trên trang Đăng ký học phần (OCR offline, không tốn phí)
- Tự đăng nhập qua **reCAPTCHA v2** (qua dịch vụ 2captcha, ~$3/1000 lần) hoặc
  paste cookie từ browser (miễn phí)
- Tự chọn mirror nhanh nhất trong 20 mirror, tự chuyển khi mirror chết
- Đăng ký **hết mọi môn đang mở** hoặc theo danh sách môn ưu tiên
- Xem trạng thái: môn đã ĐK, môn mở, số chỗ còn lại

## Cài đặt & sử dụng

Xem hướng dẫn đầy đủ: [`dkhp_tool/README.md`](dkhp_tool/README.md)

```bash
pip install httpx beautifulsoup4 ddddocr opencv-python-headless python-dotenv numpy pillow
cd dkhp_tool
copy .env.example .env    # điền tài khoản + API key 2captcha
python run.py mirrors     # check 20 mirror
python run.py login       # đăng nhập trước giờ mở ~10 phút
python run.py race        # đúng giờ: tự chờ + đăng ký ngay
```

## Cấu trúc

```
dkhp_tool/
  run.py             CLI chính (mirrors/login/status/register/cancel/race)
  portal.py          Client ASP.NET WebForms (login, captcha gate, postback)
  captcha_solver.py  OCR captcha 6 số: tách ký tự + ddddocr
  solver_2captcha.py reCAPTCHA v2 qua 2captcha
```

## Khai báo

Đây là tool cá nhân phục vụ đăng ký học phần của chính người viết, sử dụng tài
khoản của mình trên hệ thống của trường. Không dùng để spam/đổ bộ hệ thống.
