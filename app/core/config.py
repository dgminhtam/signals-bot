# config.py
import os
import logging
from dotenv import load_dotenv

# Load biến môi trường
load_dotenv()

# --- CẤU HÌNH PATH & FILE ---
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Data Dir
DATA_DIR = os.path.join(ROOT_DIR, "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)
DB_NAME = os.path.join(DATA_DIR, "xauusd_news.db")

# Logs Dir
LOGS_DIR = os.path.join(ROOT_DIR, "logs")
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOGS_DIR, "app.log")

IMAGES_DIR = "images"

# --- API KEYS ---
# Hỗ trợ nhiều key cách nhau bởi dấu phẩy để rotate
_keys_str = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_KEYS = [k.strip() for k in _keys_str.split(',') if k.strip()]
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else None
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- AI MODEL CONFIG ---
# Provider: 'gemini' or 'openai'
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()

# Gemini Config
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash-lite")
GEMINI_FALLBACK_MODEL = "gemini-2.0-flash-lite"

# OpenAI Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")

# Groq Config
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL_NAME = os.getenv("GROQ_MODEL_NAME", "llama-3.3-70b-versatile")

# --- OTHER SETTINGS ---
# Danh sách mã chứng khoán / Keyword
KEYWORDS_DIRECT = [r"Gold", r"XAU", r"XAUUSD", r"Precious Metal", r"Vàng", r"Commodity", r"Metals"]
KEYWORDS_CORRELATION = [
    r"USD", r"DXY", r"Greenback", r"Dollar",
    r"Fed", r"FOMC", r"Powell", r"Interest Rate",
    r"CPI", r"PPI", r"NFP", r"GDP", r"EUR", r"GBP", r"JPY"
]

# --- NEWS SOURCES CONFIG ---
# Nguồn tin chuyên sâu cho XAU/USD Trading (độ nhạy cao)
NEWS_SOURCES = [
    {
        "name": "FXStreet",
        "rss": "https://www.fxstreet.com/rss/news",
        "web": "https://www.fxstreet.com/news",
        "selector": None  # Generic fallback
    },
    {
        "name": "ForexLive",
        "rss": "https://investinglive.com/feed/news",
        "web": "https://www.forexlive.com/",
        "selector": None  # Generic fallback
    },
    {
        "name": "Investing",
        "rss": "https://www.investing.com/rss/news_25.rss",
        "web": "https://www.investing.com/news/commodities",
        "selector": None  # Generic fallback
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# --- LOGGING SETUP ---
def setup_logging():
    """Thiết lập logging: Ghi ra file + Console"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("AppLogger")

logger = setup_logging()

# WordPress Config
WORDPRESS_URL = os.getenv("WORDPRESS_URL")
WORDPRESS_USER = os.getenv("WORDPRESS_USER")
WORDPRESS_APP_PASSWORD = os.getenv("WORDPRESS_APP_PASSWORD")
WORDPRESS_LIVEBLOG_ID = os.getenv("WORDPRESS_LIVEBLOG_ID", "13092")  # ID của bài liveblog gốc

# --- TRADING CONFIG ---
TRADE_VOLUME = float(os.getenv("TRADE_VOLUME", "0.01"))