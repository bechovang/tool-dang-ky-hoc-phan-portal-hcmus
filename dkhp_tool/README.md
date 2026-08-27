# HCMUS DKHP Tool

Tool đăng ký học phần tự động cho hệ `new-portalX.hcmus.edu.vn` (HCMUS).

Đã test trực tiếp trên hệ thật (27/08/2026): vượt captcha 6 số, hủy đăng ký,
đăng ký lại — tất cả bằng HTTP thuần, không cần mở browser khi chạy.

## Cách hệ thống hoạt động (đã reverse-engineer)

```
Login.aspx ──(reCAPTCHA v2, server validate thật)──> cookie .ASPXAUTH
     │                                      ⚠ cookie KHÔNG dùng chéo mirror:
     │                                      login portal nào thì bám portal đó
     ▼
DangKyHocPhan.aspx ── cổng captcha 6 số (Handlers/Captcha.ashx)
     │                mỗi lần vào lại phải vượt lại (OCR tự giải ~100ms)
     ▼
Bảng môn: tbDSDaDK (đã ĐK) / tbDSLopMo... (mở)
     │   tick cbDK + nút btnDangKy (postback ASP.NET, kèm __VIEWSTATE)
     ▼
Kết quả trong div "divMsg" (text "thành công")
```

- Captcha 6 số: **toàn chữ số**, trộn chữ to + chữ nhỏ kiểu superscript trên nền
  nhiễu → tool tách từng ký tự bằng connected-component (OpenCV) rồi OCR từng
  ký tự (ddddocr). Sai thì server cho ảnh mới → tự retry.
- reCAPTCHA login: giải qua dịch vụ bên ngoài — ưu tiên **anticaptcha.top**
  (Việt Nam, ~33đ/lần, thanh toán nội địa; đã test live 27/08/2026: giải xong
  trong ~37s, login thành công), dự phòng **2captcha** (~$3/1000 lần). Không có
  key thì dùng `login-manual` (tool mở browser, bạn tick reCAPTCHA) hoặc dán
  cookie vào `.env` (xem "Dán cookie tay vào .env" bên dưới) — free.

## Cài đặt

```bash
pip install httpx beautifulsoup4 ddddocr opencv-python-headless python-dotenv numpy pillow playwright
python -m playwright install chromium
cp .env.example .env    # rồi điền mật khẩu + API key
```

## Lệnh

| Lệnh | Chức năng |
|---|---|
| `python run.py mirrors` | Ping 20 mirror, xếp theo tốc độ |
| `python run.py login` | Login tự động qua anticaptcha.top (VN) hoặc 2captcha — key nào có trong `.env` thì dùng cái đó; **thiếu cả hai thì tự mở browser login tay** |
| `python run.py login --all` | Login tự động một lượt cho **hết mọi mirror đang sống** (kho cookie dự phòng cho race). Mirror đã có cookie sống được bỏ qua — chạy lại bao nhiêu lần cũng chỉ tốn cho cái chết; `--force` làm lại tất cả (~33đ × số mirror phải login) |
| `python run.py login-manual` | **Login tay hàng loạt qua browser**: tool mở Chromium, tự điền tài khoản cho từng mirror chưa có cookie — bạn chỉ tick reCAPTCHA + bấm Đăng nhập, tool tự lưu + verify + chuyển mirror kế. `--mirrors 4,11` hoặc `--force` để làm lại |
| `python run.py cookie` | Paste cookie từ browser (1 mirror, không cần Playwright) |
| `python run.py sessions` | Kiểm tra cookie đã lưu mirror nào còn sống (rút từ `sessions/*.json` hoặc `.env`) |
| `python run.py status` | Xem môn đã ĐK + môn đang mở |
| `python run.py open` | **Mở sẵn trang ĐKHP trên mirror nhanh nhất có cookie sống** (dò 20 mirror; thiếu cookie thì tự login trước) — cửa sổ browser hiện sẵn ô gõ mã 6 số, bạn tự gõ và tự bấm đăng ký. **Ngày đông người:** trang không lên thì tool tự F5 (~1s/lần) tới khi lên thật; phiên chết giữa chừng thì tự login lại (~33đ) rồi mở lại trang; F5 một cổng ~12 lần không lên thì **tự dò lại 20 cổng và chuyển cổng** (ưu tiên cổng có cookie sẵn — đã chạy `login --all` thì chuyển cổng miễn phí). Đóng cửa sổ khi xong, cookie mới nhất tự lưu lại |
| `python run.py register` | **Đăng ký HẾT mọi môn đang mở** |
| `python run.py register --codes MST10019,MST10020` | Chỉ đăng ký các môn này |
| `python run.py register --dry-run` | Xem nó sẽ tick gì, không submit |
| `python run.py cancel --codes MST10019` | Hủy đăng ký |
| `python run.py race` | Chờ đến khi có môn mở → tự đăng ký NGAY |
| `python run.py race --codes MST10019` | Race chỉ với danh sách ưu tiên |

Thêm `--mirror N` (1..20) cho mọi lệnh để chỉ định mirror; mặc định tự chọn
mirror nhanh nhất.

## Dán cookie tay vào .env

Không muốn dùng Playwright? Lấy cookie trực tiếp từ browser đang login sẵn:
F12 → Application → Cookies → `new-portalN.hcmus.edu.vn`, rồi thêm vào `.env`:

```ini
PORTAL4_ASPXAUTH=C7C0CCC1...   # giá trị cookie .ASPXAUTH
PORTAL4_SESSIONID=ykeq...      # giá trị cookie ASP.NET_SessionId (tùy chọn)
PORTAL11_ASPXAUTH=...          # mỗi mirror một cặp biến riêng
```

Thứ tự ưu tiên khi tool cần cookie mirror N: `sessions/portal{N}.json` (tool tự
ghi khi login — luôn mới nhất) **trước**, biến `.env` sau. Xem tool đang rút từ
đâu: `python run.py sessions` (cột *nguồn*).

⚠ Cookie là **mỗi mirror một cái** — cookie của portal4 không dùng được cho
portal11 (server mỗi mirror có khóa riêng). Ai đã login mirror nào thì dán đúng
mirror đó.

## Cookie sống bao lâu?

Thời hạn do **server** quyết định khi phát hành cookie (mặc định ASP.NET thường
20–30 phút dạng *sliding* — mỗi lượt dùng lại được tính giờ mới), ngoài ra server
có thể hủy sớm (đăng xuất, khởi động lại). Nói cách khác: **không có con số cố
định chắc chắn**, đừng để cookie nằm quá lâu trước giờ chạy.

- Ngay khi login xong, tool in hạn ghi trong cookie: `.ASPXAUTH hết hạn lúc ...`
  — đó là trần trên cùng, thực tế có thể chết sớm hơn.
- Kiểm tra thật (miễn phí, 1 request/mirror) bất cứ lúc nào:
  `python run.py sessions` → hiện SỐNG/CHẾT từng mirror.
- Chết mấy cái thì chạy lại `python run.py login --all` — nó chỉ login lại đúng
  mấy cái chết, không tốn tiền cho cái còn sống.

## `race` chạy như thế nào? Có sợ bị ban không?

Cơ chế (code: `cmd_race` trong `run.py`):

1. Khởi động: dò 20 mirror **1 lần duy nhất** → chọn mirror nhanh nhất còn
   cookie sống.
2. Vòng lặp canh: mở trang DKHP xem môn mục tiêu xuất hiện chưa — chưa thì ngủ
   ~1 giây (`POLL_INTERVAL` + ngẫu nhiên 0–0.4s cho đỡ đều đặn như máy) rồi xem
   lại; môn vừa ló là submit **NGAY** trong vài chục milisecond.
3. Mirror đang dùng sự cố (sập / văng cookie): ngủ 2 giây → chuyển sang mirror
   dự phòng có cookie sống (kho cookie do `login --all` tạo), không dò lại từ đầu.

Nhịp request — so sánh để yên tâm:

| Hoạt động | Tần suất |
|---|---|
| `race` đang canh | **~1 request/giây, trên 1 mirror duy nhất** |
| Sinh viên bấm F5 thủ công hồi hộp | 3–5 lần/giây là bình thường |
| `login --all` | tuần tự từng mirror, nghỉ 1 giây giữa các cái |

Tức là `race` chạy **ngang một người ngồi F5**, nhẹ hơn kiểu spam thật — ngày mở
đăng ký server chịu hàng nghìn sinh viên cùng lúc. Tool cũng cố ý: không dập
nhiều mirror song song, luôn sleep giữa các lượt, cộng jitter ngẫu nhiên.

Ba cách **tự làm mình bị chú ý** — tránh:

1. Mở nhiều cửa sổ `race` cùng lúc.
2. Tụt `POLL_INTERVAL` xuống dưới 0.8 (mặc định 1.0 là đẹp).
3. Chạy `login --all --force` đi đi lại lại nhiều lần trong vài phút (tốn tiền
   vô ích + tạo 20 lượt login dồn dập).

## Kịch bản ngày đăng ký (khuyến nghị)

1. **Trước giờ mở** (~10-15 phút):
   ```bash
   python run.py mirrors                     # xem mirror nào nhanh
   python run.py login --all                 # login tự động mọi mirror còn thiếu (~33đ/cái)
   #  (không muốn tốn tiền: python run.py login-manual — tick reCAPTCHA tay)
   python run.py sessions                    # xác nhận mấy mirror đã có cookie sống
   ```
   Tool sẽ bỏ qua mirror đã có cookie còn sống — chạy bao nhiêu lần cũng không
   phải login lại cái cũ.
2. **Đúng giờ**: `python run.py race` — tự refresh, vượt captcha, submit ngay
   khi môn xuất hiện. Mirror chết → **chuyển sang mirror có cookie dự phòng
   trước** (miễn phí), chỉ khi hết cookie dự phòng mới tốn 2captcha login lại.
3. Xem kết quả: `python run.py status`.

## Lưu ý quan trọng

- **Không commit** `.env` và `sessions/` (đã có trong `.gitignore`) — bên trong
  là mật khẩu và cookie đăng nhập.
- Mật khẩu đã từng dán vào chat/terminal → nên **đổi mật khẩu** sau khi xong.
- Chạy quá dồn dập (nhiều thread đánh 20 mirror cùng lúc) vừa dễ bị chặn vừa
  làm hệ thống nặng thêm cho mọi người — tool cố ý chạy 1 mirror chính, thăm dò
  khoảng ~1 giây/lần.
- Đăng ký "hết mọi môn" có thể vướng trần tín chỉ / trùng lịch → server sẽ báo
  trong thông điệp; những môn thừa phải tự `cancel` sau.
