# 🤖 AI Gold Signals Bot (XAU/USD)

Bot tín hiệu Vàng (XAU/USD) tự động hóa hoàn toàn: Quét tin tức -> Phân tích Kỹ thuật -> AI Tổng hợp -> Bắn tín hiệu Telegram.
Được xây dựng với kiến trúc **Clean Architecture** dễ bảo trì và mở rộng.

---

## 🚀 Tính Năng Nổi Bật

### 1. Phân Tích Đa Chiều (News + Technical)
- **News**: Quét 4 nguồn tin uy tín (Kitco, Investing, GoldPrice, ForexLive) để lọc tin tức ảnh hưởng.
- **Technical**: Tự động vẽ chart H1, tính RSI, Trend EMA, và các mức Support/Resistance Fibonacci.
- **AI Synthesis**: Kết hợp cả tin tức và dữ liệu kỹ thuật để đưa ra nhận định "Sniper" (Bullish/Bearish/Sideway).

### 2. Ba Khung Giờ Chiến Lược (Strategic High-Volume Timeframes)
Scheduler được tối ưu để hoạt động vào các thời điểm thanh khoản cao nhất:
- **07:00 (Phiên Á)**: Tổng hợp tin đêm, setup plan cho ngày mới.
- **13:30 (Pre-London)**: Chuẩn bị cho phiên Âu đầy biến động.
- **19:00 (Pre-New York)**: Quét tin nóng trước giờ Mỹ mở cửa (Giờ quan trọng nhất).

### 3. Real-time Breaking Alert 🚨
- Một Worker riêng chạy **mỗi 15 phút**.
- Chỉ báo động khi có tin CỰC NÓNG (War, Fed Surprise, CPI/NFP) có khả năng làm giá chạy ngay lập tức.
- Bỏ qua các tin nhận định chung chung.

### 4. Smart Scheduling
- **Weekend Mode**: Tự động ngủ đông vào Thứ 7, Chủ Nhật (do thị trường Gold đóng cửa) để tiết kiệm tài nguyên.
- **Rate Limit Safe**: Cơ chế delay thông minh giúp tránh bị chặn bởi các trang tin.

---

## 📂 Cấu Trúc Dự Án (Clean Architecture)

```text
signals-bot/
├── app/
│   ├── core/           # Cấu hình & Database nền tảng
│   │   ├── config.py
│   │   └── database.py
│   ├── services/       # Logic nghiệp vụ (Trái tim của Bot)
│   │   ├── ai_engine.py    # Giao tiếp Google Gemini AI
│   │   ├── news_crawler.py # Xử lý RSS & Parsing
│   │   ├── charter.py      # Vẽ Chart & Tính toán Indicator
│   │   └── telegram_bot.py # Gửi tin nhắn Telegram
│   ├── jobs/           # Các quy trình chạy định kỳ
│   │   ├── daily_report.py # Báo cáo Full (Chart + AI + News)
│   │   └── realtime_alert.py # Báo cáo nhanh (Breaking News)
│   └── utils/          # Tiện ích
│       └── prompts.py      # Chứa lời nhắc (Prompt) cho AI
├── main.py             # File điều khiển trung tâm (Entry Point)
├── requirements.txt    # Thư viện phụ thuộc
├── .env                # Biến môi trường (MẬT)
└── xauusd_news.db      # Database SQLite (Tự tạo)
```

---

## 🛠️ Cài Đặt & Cấu Hình

### 1. Cài đặt Python & Thư viện
Yêu cầu Python 3.9 trở lên.
```bash
pip install -r requirements.txt
```

### 2. Cấu hình .env
Tạo file `.env` tại thư mục gốc và điền thông tin:

```env
# Gemini API Key (Lấy tại aistudio.google.com)
GEMINI_API_KEY=AIzaSy...

# Telegram Config (Tạo bot qua @BotFather)
TELEGRAM_BOT_TOKEN=7098...
TELEGRAM_CHAT_ID=-461...
```

### 3. Tùy chỉnh Prompt (Nâng cao)
Muốn thay đổi giọng văn của AI? Hãy sửa file `app/utils/prompts.py`.
- **ANALYSIS_PROMPT**: Dùng cho bài phân tích dài (Daily Report).
- **BREAKING_NEWS_PROMPT**: Dùng cho cảnh báo nhanh.

---

## 🧪 Testing & Commands (Kiểm Thử Chức Năng)

Để đảm bảo bot hoạt động ổn định, bạn có thể chạy test từng thành phần riêng lẻ bằng các câu lệnh sau:

### 1. Test Daily Report (Báo Cáo Tổng Hợp)
Chạy quy trình quét tin, phân tích AI, vẽ chart và gửi báo cáo Daily.
Lưu ý: Job này chỉ gửi bài nếu có tin mới (status='NEW'). Nếu không có tin, nó sẽ log warning.

```bash
python -m app.jobs.daily_report
```

### 2. Test Real-time Alert (Cảnh Báo Nóng)
Chạy worker quét tin nóng trong 20 phút gần nhất. Nếu phát hiện tin Breaking News chưa alert, nó sẽ gửi ngay lập tức.

```bash
python -m app.jobs.realtime_alert
```

### 3. Test Manual Mode (Chế Độ Thủ Công)
Ép buộc chạy toàn bộ quy trình Main Flow ngay lập tức (Bỏ qua lịch trình scheduler, bỏ qua check ngày nghỉ). Rất hữu ích khi muốn test full flow.

```bash
python main.py --manual
```

### 4. Test Charter Service (Vẽ Biểu Đồ)
Kiểm tra khả năng kết nối MT5/yfinance và vẽ biểu đồ.
Kết quả sẽ tạo file ảnh tại `images/chart_price.png`.

```bash
python -m app.services.charter
```

### 5. Test Economic Calendar (Lịch Kinh Tế)
Test module crawler lịch kinh tế và cơ chế gửi cảnh báo sự kiện (Pre-alert / Post-alert).

```bash
python -m app.jobs.economic_calendar
```

Hoặc chạy script giả lập để test bắn tin (nếu có):
```bash
python test_simulation_ec.py
```

### 6. Test Utility Scripts
Nếu bạn có các script test nhỏ lẻ khác:

*   **Test Crawl Tin Tức**: `python -m app.services.news_crawler` (In ra danh sách tin quét được)
*   **Test Telegram Bot**: `python -m app.services.telegram_bot` (Gửi tin nhắn test)

---

## ▶️ Vận Hành (Production)

### Chạy Bot (Auto Mode)
Chỉ cần chạy file `main.py`. Bot sẽ tự khởi động scheduler và các job theo lịch trình định sẵn.

```bash
python main.py
```

### Theo dõi Log
Bot sẽ in log chi tiết ra màn hình console và lưu vào file `app.log`.
- `INFO`: Thông báo bình thường (Quét tin, Gửi bài).
- `WARNING`: Lỗi nhẹ (Không lấy được tin 1 nguồn, AI response lag).
- `ERROR`: Lỗi cần kiểm tra (Mất kết nối DB, API Key lỗi).