# Hướng Dẫn Cài Đặt và Chạy Dự Án Data Ingestion (Signals Bot)

Tài liệu này hướng dẫn chi tiết từng bước để cài đặt môi trường, chạy bot và debug lỗi.

## 1. Yêu cầu Hệ thống
- Python 3.10 trở lên.
- Đã cài đặt Git.
- VS Code (Khuyên dùng để debug).

## 2. Cài đặt Môi trường

### Bước 2.1: Tạo môi trường ảo (Virtual Environment)
Mở terminal tại thư mục gốc của dự án (`data-ingestion`) và chạy lệnh:

```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate

# Mac/Linux
python3 -m venv .venv
source .venv/bin/activate
```
*Sau khi chạy, bạn sẽ thấy `(.venv)` ở đầu dòng lệnh.*

### Bước 2.2: Cài đặt thư viện dependencies
Chạy lệnh sau để cài đặt các thư viện cần thiết:

```bash
pip install -r requirements.txt
```
*(Nếu chưa có file `requirements.txt`, bạn có thể cài thủ công các thư viện sau)*:
```bash
pip install requests feedparser python-dotenv pandas matplotlib mplfinance yfinance google-generativeai
```

### Bước 2.3: Cấu hình biến môi trường (.env)
Tạo file `.env` tại thư mục gốc và điền các thông tin sau (sửa lại cho đúng với của bạn):

```ini
GEMINI_API_KEY=your_gemini_key_here
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## 3. Chạy Dự án (Run)

### Chạy toàn bộ quy trình (Main Flow)
Đây là lệnh chính để bot lấy tin -> phân tích -> vẽ chart -> gửi Telegram:

```bash
python run_analysis.py
```
**Quy trình chạy:**
1.  **Lấy tin**: Quét RSS feeds từ các nguồn cấu hình.
2.  **Vẽ chart**: Tải dữ liệu giá vàng (XAUUSD) và vẽ Fibonacci H1.
3.  **AI Phân tích**: Gửi tin tức + chart prompt sang Google Gemini.
4.  **Gửi Telegram**: Format tin nhắn đẹp và gửi vào group.

## 4. Hướng dẫn Debug (Sửa lỗi)

### 4.1 Debug từng thành phần (Khuyên dùng)
Dự án có sẵn các file script nhỏ để test từng phần riêng biệt.

#### A. Kiểm tra nguồn tin RSS
Nếu bot không lấy được tin mới, hãy chạy file này để xem kết nối đến các trang tin có ổn không:

```bash
python debug_rss.py
```
*Output sẽ hiển thị trạng thái kết nối (200 OK) và số lượng bài viết tìm thấy.*

#### B. Kiểm tra vẽ biểu đồ
Nếu chart không được gửi hoặc bị lỗi, chạy riêng file này để xem lỗi cụ thể:

```bash
python charter.py
```
*Kiểm tra thư mục `images/` xem file `chart_price.png` có được tạo không.*

#### C. Kiểm tra luồng Logic (Test Flow)
Chạy script kiểm tra tổng thể các hàm nhỏ (Database, Import, Logic keyword):

```bash
python test_flow.py
```

### 4.2 Debug bằng VS Code (Nâng cao)

Để debug chuyên nghiệp (đặt Breakpoint, xem biến), hãy sử dụng cấu hình `launch.json` đã được tạo sẵn.

1.  Mở tab **Run and Debug** bên trái VS Code (hoặc ấn `Ctrl+Shift+D`).
2.  Ở menu dropdown phía trên, bạn sẽ thấy các tùy chọn:
    -   `Run Main Analysis` (Chạy luồng chính)
    -   `Debug RSS Feed` (Chỉ debug tin tức)
    -   `Test Chart Generator` (Chỉ debug vẽ chart)
3.  Chọn một mode và ấn nút ▶️ (Play).
4.  **Cách đặt Breakpoint**: Click vào lề trái số dòng code (ví dụ dòng 90 `run_analysis.py`) để dừng chương trình tại đó và xem giá trị biến.

## 5. Các lỗi thường gặp

1.  **Lỗi `Missing GEMINI_API_KEY`**:
    -   Kiểm tra file `.env` đã có key chưa.
    -   Đảm bảo đã `load_dotenv()` (Code đã tự xử lý, chỉ cần file .env đúng vị trí).

2.  **Lỗi `yfinance failed to download`**:
    -   Do mạng hoặc IP bị chặn. Thử đổi mạng hoặc VPN.
    -   Kiểm tra lại symbol trong code `charter.py`.

3.  **Lỗi Import**:
    -   Đảm bảo bạn đã activate venv (`.venv`).
    -   Chạy lại `pip install ...`.
