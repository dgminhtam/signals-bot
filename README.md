# 🤖 Signals Bot - XAU/USD Trading Assistant

> **Hệ thống tự động phân tích tin tức, dự báo xu hướng và giao dịch XAU/USD sử dụng AI và phân tích kỹ thuật (AsyncIO High Performance).**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![AI](https://img.shields.io/badge/AI-Gemini%20%7C%20GPT-orange.svg)](https://ai.google.dev/)
[![AsyncIO](https://img.shields.io/badge/Architecture-AsyncIO-purple.svg)](https://docs.python.org/3/library/asyncio.html)

---

## 📋 Tổng Quan

**Signals Bot** đã được nâng cấp hoàn toàn lên kiến trúc **AsyncIO**. Hệ thống giao dịch tự động hoàn chỉnh kết hợp:
- 🌐 **News Crawler**: `curl_cffi` (Browser TLS Fingerprint) async requests.
- 🤖 **AI Analysis**: Gemini/OpenAI/Groq Async Clients.
- 📊 **Technical Analysis**: ThreadPoolExecutor cho các tác vụ CPU-bound.
- ⚡ **Real-time Alert**: Quét và cảnh báo < 1s độ trễ.
- 💰 **Auto Trading**: MT5 Socket Bridge Non-blocking I/O.

---

## 🔥 Tính Năng Chính

### 1. News Aggregation (HFT Mode)
- **Nguồn tin chuyên sâu**: FXStreet, ForexLive, Investing.com
- **Technology**: 100% Async crawling.
- **Lookback**: 5 phút (Optimized for High-Frequency).

### 2. AI-Powered Analysis
- **Hỗ trợ**: Gemini Flash, GPT-4o, Llama 3 (via Groq).
- **Mode**: Phân tích song song (Concurrent Analysis).

### 3. Real-time Alert System
- **Frequency**: Quét mỗi 1 phút.
- **Delivery**: Telegram (Text/Image) + WordPress Liveblog.

### 4. Auto Trading (Expert Advisor)
- **MT5 Bridge**: Kết nối không chặn (Non-blocking Socket).
- **Execution**: Vào lệnh cực nhanh (< 100ms).
- **Strategy**: Trend Following + Fibonacci.

### 5. Economic Calendar
- **Hybrid**: JSON API + HTML Parsing (Async).
- **Alert**: Pre-News & Post-News Reaction.

---

## 📂 Cấu Trúc Dự Án

```
signals-bot/
├── app/
│   ├── core/               # Async DB & Config
│   ├── jobs/               # Async Jobs (Report, Alert, Calendar)
│   ├── services/           # Async Services (AI, News, Trader...)
│   └── utils/
├── data/                   # SQLite (WAL Mode)
├── main.py                 # Async Entry Point
└── requirements.txt
```

---

## 🚀 Cài Đặt & Chạy

### 1. Cài Đặt
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Chạy Bot (Scheduler Mode)
Để chạy toàn bộ hệ thống (tất cả các tác vụ):
```bash
python main.py
```
*Tự động chạy: Crawler, Daily Report, Real-time Alert, Economic Calendar, Auto Trader theo lịch trình.*

### 3. Chạy Manual (Test chức năng riêng lẻ)
Nếu bạn muốn chạy thử nghiệm các tính năng ngay lập tức:

```bash
# 1. Chạy Full Flow (Crawler -> Report -> Alert)
python main.py --manual

# 2. Chỉ chạy Daily Report
python main.py --report

# 3. Chỉ chạy Real-time Alert
python main.py --alert

# 4. Chỉ chạy Auto Trader Strategy
python main.py --trade

# 5. Chỉ chạy Crawler (Lấy tin mới nhất)
python main.py --crawler

# 6. Chỉ chạy Economic Calendar Check
python main.py --calendar
```

---

## ⚠️ Lưu Ý Quan Trọng
1. **AsyncIO**: Codebase sử dụng `async/await` triệt để. Không dùng các thư viện blocking (như `requests` hay `time.sleep`) trong core loops.
2. **MT5**: Cần chạy EA `SimpleDataServer` trên MT5 Terminal trước khi chạy Bot.
3. **Database**: SQLite chạy ở chế độ WAL (Write-Ahead Logging) để hỗ trợ tốt hơn cho async concurrency.

---

## 📧 Liên Hệ
Project Link: [https://github.com/dgminhtam/signals-bot](https://github.com/dgminhtam/signals-bot)

**⚠️ Disclaimer**: Bot phục vụ mục đích nghiên cứu. Luôn test kỹ trên Demo.
