# 🤖 Signals Bot - XAU/USD Trading Assistant

> **Hệ thống tự động phân tích tin tức, dự báo xu hướng và giao dịch XAU/USD sử dụng AI và phân tích kỹ thuật.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![AI](https://img.shields.io/badge/AI-Gemini%20%7C%20GPT-orange.svg)](https://ai.google.dev/)

---

## 📋 Tổng Quan

**Signals Bot** là một hệ thống giao dịch tự động hoàn chỉnh kết hợp:
- 🌐 **News Crawler** với công nghệ Anti-Detect Browser (`curl_cffi`)
- 🤖 **AI Analysis** (Gemini/OpenAI/Groq) phân tích tâm lý thị trường
- 📊 **Technical Analysis** với Fibonacci, MA, và Price Action
- ⚡ **Real-time Alert** phát hiện Breaking News trong < 1 phút
- 💰 **Auto Trading** tự động vào lệnh MT5 dựa trên tín hiệu

---

## 🔥 Tính Năng Chính

### 1. News Aggregation (HFT Mode)
- **Nguồn tin chuyên sâu**: FXStreet, ForexLive, Investing.com
- **Technology Stack**: `curl_cffi` (Browser TLS Fingerprint) + `newspaper3k` (Content Extraction)
- **Lookback**: 5 phút (Optimized for High-Frequency)
- **Database**: SQLite với indexing tối ưu

### 2. AI-Powered Analysis
- **Multi-Provider Support**: Gemini Flash Lite, GPT-4o Mini, Groq Llama
- **Context Awareness**: So sánh với phiên trước (Memory)
- **Output**: Sentiment Score, Trend, Bullet Points, Trading Suggestion

### 3. Real-time Alert System
- **Frequency**: Quét mỗi 1 phút
- **Pre-filter**: Từ khóa mạnh (CPI, Fed, NFP...) để tiết kiệm token
- **Delivery**: Telegram (Text/Image) + WordPress Liveblog
- **Localization**: Tiếng Việt với Quote từ bài gốc

### 4. Auto Trading (Expert Advisor)
- **Execution**: MT5 Bridge (Socket Connection)
- **Strategy**: Trend Following + Fibonacci Retracement
- **Risk Management**: Dynamic SL/TP dựa trên Fibonacci levels
- **Schedule**: Mỗi giờ tại phút :02 (sau khi nến H1 đóng)

### 5. Economic Calendar Integration
- **Source**: Investing.com Economic Calendar API
- **Frequency**: Cập nhật mỗi 5 phút
- **Features**:
  - Tự động theo dõi các sự kiện kinh tế quan trọng
  - Lọc theo độ ưu tiên (High/Medium/Low Impact)
  - Cảnh báo trước các sự kiện ảnh hưởng đến XAU/USD
  - Tích hợp vào phân tích AI để tăng độ chính xác

---

## 📂 Cấu Trúc Dự Án

```
signals-bot/
├── app/                    # Core Application Logic
│   ├── core/              
│   │   ├── config.py       # Configuration & Environment
│   │   └── database.py     # SQLite Operations
│   ├── jobs/              
│   │   ├── daily_report.py # Daily Market Summary
│   │   ├── realtime_alert.py # Breaking News Alert
│   │   └── economic_worker.py # Economic Calendar
│   ├── services/          
│   │   ├── news_crawler.py # News Scraping (curl_cffi)
│   │   ├── ai_engine.py    # AI Integration
│   │   ├── charter.py      # Technical Analysis
│   │   ├── trader.py       # Auto Trading Logic
│   │   ├── telegram_bot.py # Telegram Publisher
│   │   └── wordpress_service.py # WordPress Liveblog
│   └── utils/             
│       ├── prompts.py      # AI System Prompts
│       └── helpers.py      # Utility Functions
├── data/                   # Database Storage
│   └── xauusd_news.db
├── logs/                   # Application Logs
│   └── app.log
├── mql5/                   # MetaTrader 5 Expert Advisor
│   ├── SimpleDataServer.mq5
│   └── SimpleDataServer.ex5
├── scripts/                # Development/Testing Scripts
│   ├── check_models.py
│   ├── test_content_fetch.py
│   └── test_investing.py
├── images/                 # Generated Charts
├── main.py                 # Entry Point
└── requirements.txt        # Python Dependencies
```

---

## 🚀 Cài Đặt

### 1. Yêu Cầu Hệ Thống
- **Python**: 3.10+
- **MetaTrader 5**: Phiên bản Desktop (Optional, for Auto Trading)
- **OS**: Windows (MT5 requirement)

### 2. Clone Repository
```bash
git clone https://github.com/yourusername/signals-bot.git
cd signals-bot
```

### 3. Cài Đặt Dependencies
```bash
# Tạo Virtual Environment (Khuyến nghị)
python -m venv .venv
.venv\Scripts\activate  # Windows

# Cài đặt thư viện
pip install -r requirements.txt
```

### 4. Cấu Hình Environment
Tạo file `.env` tại thư mục gốc:

```env
# AI Provider (gemini/openai/groq)
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_key_here
OPENAI_API_KEY=your_openai_key_here
GROQ_API_KEY=your_groq_key_here

# Telegram Bot
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# WordPress (Optional)
WORDPRESS_URL=https://yoursite.com
WORDPRESS_USER=admin
WORDPRESS_APP_PASSWORD=xxxx xxxx xxxx xxxx
WORDPRESS_LIVEBLOG_ID=13092
```

### 5. Kiểm Tra Kết Nối AI
```bash
python scripts/check_models.py
```

---

## 🎮 Sử Dụng

### Chế Độ Tự Động (Scheduler)
```bash
python main.py
```
Bot sẽ tự động chạy theo lịch trình:
- **07:00, 13:30, 19:00**: Daily Report
- **Mỗi 1 phút**: Real-time Alert
- **Mỗi giờ (:02)**: Auto Trading

### Chế Độ Thủ Công (Manual Testing)
```bash
# Chạy Daily Report
python main.py --report

# Chạy Real-time Alert
python main.py --alert

# Chạy Auto Trader
python main.py --trade

# Chỉ quét tin (không phân tích)
python main.py --crawler
```

---

## 🔧 Cấu Hình Nâng Cao

### Thay Đổi AI Provider
Sửa file `.env`:
```env
AI_PROVIDER=openai  # hoặc gemini, groq
```

### Tùy Chỉnh Nguồn Tin
Sửa file `app/core/config.py`:
```python
NEWS_SOURCES = [
    {
        "name": "YourSource",
        "rss": "https://...",
        "web": "https://...",
        "selector": None
    }
]
```

### Điều Chỉnh Lịch Trình
Sửa file `main.py` tại hàm `run_schedule()`.

---

## 📊 Kiến Trúc Kỹ Thuật

### News Crawler Pipeline
```
RSS Feed → curl_cffi (TLS Bypass) → newspaper3k (Parse) 
→ Keyword Filter → DB Storage → AI Analysis
```

### AI Analysis Flow
```
News + Technical Data + Previous Report → AI (Gemini/GPT)
→ Structured Output (JSON Schema) → Telegram/WordPress
```

### Trading Execution
```
Hourly Trigger → Market Data (TradingView/MT5) 
→ Trend Analysis → Fibonacci Levels → Order Execution (MT5)
```

---

## 🛠️ Troubleshooting

### Lỗi "curl_cffi không tải được"
```bash
pip install --upgrade curl-cffi
```

### Lỗi "Gemini API QuotaExceeded"
- Thêm nhiều API Keys vào `.env` (cách nhau bởi dấu phẩy)
- Hoặc chuyển sang OpenAI/Groq

### MT5 không kết nối
- Kiểm tra MT5 đang chạy
- Enable Algorithm Trading trong MT5
- Chạy EA `SimpleDataServer.ex5`

---

## 📝 Roadmap

- [x] Multi-source News Crawler
- [x] AI Integration (3 providers)
- [x] Real-time Alert System
- [x] Auto Trading Module
- [x] WordPress Integration
- [ ] Backtesting Framework
- [ ] Risk Management Dashboard
- [ ] Mobile App (React Native)

---

## 🤝 Đóng Góp

Mọi đóng góp đều được chào đón! Vui lòng:
1. Fork dự án
2. Tạo branch tính năng (`git checkout -b feature/AmazingFeature`)
3. Commit thay đổi (`git commit -m 'Add some AmazingFeature'`)
4. Push lên branch (`git push origin feature/AmazingFeature`)
5. Mở Pull Request

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.

---

## 📧 Liên Hệ

Project Link: [https://github.com/yourusername/signals-bot](https://github.com/yourusername/signals-bot)

---

**⚠️ Disclaimer**: Bot này chỉ phục vụ mục đích giáo dục và nghiên cứu. Giao dịch tài chính có rủi ro cao. Luôn test kỹ trên tài khoản Demo trước khi sử dụng tiền thật.
