# config.py
import os
import logging
from dotenv import load_dotenv

# Load biến môi trường
load_dotenv()

# --- CẤU HÌNH PATH & FILE ---
DB_NAME = "xauusd_news.db"
LOG_FILE = "app.log"
IMAGES_DIR = "images"

# --- API KEYS ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- OTHER SETTINGS ---
# Danh sách mã chứng khoán / Keyword
KEYWORDS_DIRECT = [r"Gold", r"XAU", r"XAUUSD", r"Precious Metal", r"Vàng", r"Commodity", r"Metals"]
KEYWORDS_CORRELATION = [
    r"USD", r"DXY", r"Greenback", r"Dollar",
    r"Fed", r"FOMC", r"Powell", r"Interest Rate",
    r"CPI", r"PPI", r"NFP", r"GDP"
]

RSS_SOURCES = [ 
    {"name": "Google News (Gold)", "url": "https://news.google.com/rss/search?q=XAUUSD+Gold+Price+Analysis&hl=en-US&gl=US&ceid=US:en"},
    {"name": "CNBC World", "url": "https://www.cnbc.com/id/100727362/device/rss/rss.html"}
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
