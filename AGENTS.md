# AGENTS.md — Hướng dẫn cho AI agent thao tác với dự án này

> Bạn (AI agent) đang giúp một **sinh viên không biết kỹ thuật** dùng tool đăng ký
> học phần HCMUS. Đọc kỹ file này trước khi làm bất cứ điều gì.

## Về dự án

Tool đăng ký học phần tự động cho `new-portal1..20.hcmus.edu.vn` (portal sinh viên
HCMUS). Toàn bộ logic nằm trong thư mục `dkhp_tool/` (Python, không cần browser
khi chạy). Đã được test trực tiếp trên hệ thật ngày 27/08/2026.

- `dkhp_tool/run.py` — CLI chính, mọi thao tác đi qua đây
- `dkhp_tool/portal.py` — client HTTP (login, captcha, đăng ký/hủy môn)
- `dkhp_tool/captcha_solver.py` — OCR captcha 6 số (offline, miễn phí)
- `dkhp_tool/browser_login.py` — login tay qua browser Chromium
- Chi tiết kỹ thuật đầy đủ: đọc `dkhp_tool/README.md`

## Luật bất di bất dịch (bắt buộc tuân theo)

1. **Trả lời bằng tiếng Việt, đơn giản, không thuật ngữ kỹ thuật.** Người dùng
   không biết lập trình. "Cookie" thì giải thích là "thẻ vào cửa của web trường".
2. **Không bao giờ commit / push / hiển thị** file `.env` hoặc thư mục
   `dkhp_tool/sessions/` (chứa mật khẩu và thẻ vào cửa). Chúng đã nằm trong
   `.gitignore` — đừng "sửa" cái đó.
3. **Đăng ký / hủy môn là hành động THẬT** trên học bạ của người dùng. Trước khi
   chạy `register`, `cancel`, luôn đọc to danh sách môn sẽ bị tác động và chờ
   người dùng gõ "đồng ý". `race` thì phải có người dùng chủ động yêu cầu.
4. **Không tăng tốc độ thăm dò** (POLL_INTERVAL dưới 0.8s) và không chạy nhiều
   tiến trình race cùng lúc — làm trường phát hiện và khóa tài khoản.
5. Mật khẩu người dùng đưa vào chat: chỉ ghi vào `.env`, sau đó nhắc họ đổi mật
   khẩu nếu họ từng dán công khai nơi khác.

## Cài đặt (khi người dùng nói "cài giúp tôi" / "setup")

Windows, cần Python 3.10+. Chạy lần lượt, báo người dùng đang làm gì:

```bash
python --version        # nếu lỗi => cài Python từ python.org, tích chọn "Add to PATH"
cd dkhp_tool
pip install httpx ddddocr opencv-python-headless python-dotenv numpy playwright
python -m playwright install chromium
```

Lưu ý môi trường Windows:
- Đường dẫn có dấu cách ("GIT CLONE") — luôn bọc path trong dấu nháy.
- Console Windows hay lỗi font tiếng Việt: chạy python kèm
  `set PYTHONIOENCODING=utf-8` (cmd) hoặc `$env:PYTHONIOENCODING='utf-8'` (PowerShell)
  nếu thấy lỗi `UnicodeEncodeError`.
- Nếu `pip` báo lỗi quyền: thử `python -m pip install ...`.

Sau khi cài xong, cấu hình `.env` (xem mục dưới) rồi chạy health-check:

```bash
python run.py mirrors    # phải thấy danh sách mirror + thời gian phản hồi
```

## Cấu hình .env (bắt buộc trước khi dùng)

Copy `dkhp_tool/.env.example` thành `dkhp_tool/.env` rồi điền:

- `USERNAME_SV`, `PASSWORD_SV` — tài khoản portal của người dùng (hỏi họ)
- `ANTICAPTCHA_API_KEY` — key anticaptcha.top (dịch vụ VN, ~33đ/lần giải
  reCAPTCHA, thanh toán chuyển khoản nội địa). Tool ưu tiên key này.
- `TWOCAPTCHA_API_KEY` — dự phòng nếu không dùng anticaptcha.top
- `MIRROR` — để 0 (tự chọn)
- Cả hai key đều có thể bỏ trống (xem "Các cách đăng nhập" bên dưới)

## Các cách đăng nhập — giải thích cho người dùng như sau

| Cách | Khi nào | Chi phí | AI làm gì |
|---|---|---|---|
| `login-manual` (browser) | Miễn phí, nhiều mirror cùng lúc | 0đ | AI chạy lệnh, **con người** tick reCAPTCHA trong cửa sổ Chromium hiện ra. AI KHÔNG tick được hộ — phải mời người dùng nhìn màn hình |
| `login` (tự động) | Cần tự động 100%, ví dụ tool tự login lại giữa đêm | ~33đ/lần (anticaptcha.top) | AI tự chạy: gửi reCAPTCHA qua dịch vụ, nhận token, login, lưu cookie (~30-40 giây). Lệnh `login` cũng tự báo số dư anticaptcha.top |
| Dán cookie vào `.env` | Người dùng đã login sẵn trong browser thường, không muốn cài Playwright | 0đ | Hướng dẫn họ: F12 > Application > Cookies > `new-portalN.hcmus.edu.vn`, copy giá trị `.ASPXAUTH` (và `ASP.NET_SessionId`) rồi ghi vào `.env` dạng `PORTAL4_ASPXAUTH=...`, `PORTAL4_SESSIONID=...` — mỗi mirror một cặp. Tool ưu tiên cookie `sessions/*.json` hơn, `.env` chỉ dùng cho mirror chưa có file |

Nếu người dùng không có key dịch vụ nào: bỏ trống cả hai, mọi thứ vẫn chạy bình
thường bằng login-manual hoặc cookie dán tay.

## Sổ tay lệnh (chạy trong `dkhp_tool/`)

| Người dùng nói | Lệnh chạy | Giải thích cho họ |
|---|---|---|
| "xem portal nào sống" | `python run.py mirrors` | "thử tiếng 20 cổng web, cái nào nhanh nhất" |
| "đăng nhập sẵn" | `python run.py login-manual` | "mở browser, anh/chị tick ô reCAPTCHA giúp tôi nhé" |
| "đăng nhập tự động" | `python run.py login` | cần `ANTICAPTCHA_API_KEY` trong .env — tool tự giải reCAPTCHA (~33đ/lần), tự báo số dư |
| "đăng nhập sẵn tất cả cổng" | `python run.py login --all` | login tự động lần lượt mọi mirror đang sống (~33đ × số mirror còn thiếu — cái đã có cookie sống thì bỏ qua). `--force` làm lại hết. Sau lệnh này tool in hạn của từng cookie |
| "kiểm tra phiên đăng nhập" | `python run.py sessions` | "xem còn giữ thẻ vào cửa của mấy cổng" (rút từ sessions/*.json hoặc .env) |
| "tôi có cookie, thêm vào giùm" | ghi `PORTAL{N}_ASPXAUTH=...` vào `.env` rồi chạy `python run.py sessions` | "dán thẻ vào cửa của cổng N vào file cấu hình, kiểm tra ngay xem còn dùng được không" |
| "xem môn" | `python run.py status` | "liệt kê môn đã đăng + môn đang mở" |
| "mở trang lên cho tôi tự bấm" | `python run.py open` | tool dò 20 cổng + dùng cookie sẵn (hết thì tự login lại), mở cửa sổ Chromium tại trang ĐKHP với ô gõ mã 6 số — **người dùng tự gõ mã, tự tick môn, tự bấm**. Ngày nghẽn: tự F5 ~1s/lần tới khi trang lên; phiên chết thì tự login lại + mở lại trang; cổng nghẽn đặc (F5 ~12 lần hụt) thì tự dò lại 20 cổng rồi **chuyển cổng**. Đóng cửa sổ khi xong là cookie tự lưu |
| "đăng ký hết" | `python run.py register` | ⚠️ hành động thật — đọc danh sách + chờ "đồng ý" |
| "đăng ký mấy môn X,Y" | `python run.py register --codes X,Y` | như trên nhưng chọn lọc |
| "hủy môn X" | `python run.py cancel --codes X` | ⚠️ hành động thật — xác nhận trước |
| "canh giờ mở đăng ký" | `python run.py race` | tool tự chờ, môn vừa mở là tự đăng ký NGAY |
| "canh mấy môn X,Y" | `python run.py race --codes X,Y` | như trên nhưng chỉ môn trong danh sách |

Quy trình ngày đăng ký chuẩn (hướng dẫn người dùng theo đúng thứ tự):

1. Trước 10-15 phút: `mirrors` → `login --all` (tự động, ~33đ/mirror) hoặc
   `login-manual` (tick reCAPTCHA tay, miễn phí) → `sessions`
2. Đúng giờ: `race` (hoặc `race --codes ...` nếu chỉ cần vài môn)
3. Xong: `status` để xác nhận kết quả

## Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân & cách xử lý |
|---|---|
| `NO mirror responded` | Mạng/chặn DNS. Đợi 1-2 phút chạy lại `mirrors`. Đúng giờ mở đăng ký portal hay nghẽn — bình thường |
| `auth lost` / bị đá về Login | Cookie hết hạn. Chạy `login --all` (tự động mọi mirror còn thiếu, tốn phí) hoặc `login-manual --force` (tick tay, miễn phí). Cookie không có hạn cố định chắc chắn — kiểm tra bằng `sessions` |
| `Captcha không đúng` lặp lại nhiều lần | OCR hụt ảnh — tool tự thử lại. Nếu kẹt >2 phút: chạy `login-manual` lấy session mới |
| `UnicodeEncodeError` | Thiết lập `PYTHONIOENCODING=utf-8` như mục Cài đặt |
| `playwright` lỗi/not installed | `pip install playwright` + `python -m playwright install chromium` |
| `đăng ký không thành công` kèm lý do | Đọc thông điệp server (trùng lịch, hết chỗ, vượt tín chỉ) — giải thích nguyên bản cho người dùng, gợi ý `--codes` chọn môn lại |
| Session mirror này không dùng được mirror kia | ĐÚNG THIẾT KẾ: 1 cookie = 1 mirror. Muốn dự phòng thì login riêng từng mirror |

## Khi người dùng nhờ thêm tính năng

Ưu tiên giữ tool đơn giản. Đã có: race, chọn môn, hủy môn, dự phòng mirror.
Trước khi viết code mới, kiểm tra `dkhp_tool/run.py --help` — có thể tính năng
đã tồn tại. Sửa xong thì chạy `python run.py mirrors` hoặc `status` xác nhận
không vỡ gì rồi mới trả lời người dùng.
