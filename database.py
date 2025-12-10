import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from dateutil import parser
import re
import time
import json
import sqlite3
from contextlib import contextmanager
from typing import List, Dict, Optional, Any
import config # Import config module

# --- CẤU HÌNH ---
# Sử dụng biến từ config.py
DB_NAME = config.DB_NAME
KEYWORDS = {
    "DIRECT": config.KEYWORDS_DIRECT,
    "CORRELATION": config.KEYWORDS_CORRELATION
}
HEADERS = config.HEADERS
logger = config.logger

@contextmanager
def get_db_connection():
    """Context manager để quản lý kết nối DB an toàn"""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row # Trả về Row object thay vì tuple
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Lỗi kết nối CSDL: {e}")
        raise e
    finally:
        if conn:
            conn.close()

# --- PHẦN DATABASE (MỚI) ---
def init_db() -> None:
    """Khởi tạo bảng nếu chưa có"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            # Tạo bảng articles
            c.execute('''
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY,       -- Link bài viết là khóa chính
                    source TEXT,
                    title TEXT,
                    published TEXT,
                    content TEXT,              -- Nội dung full
                    keywords TEXT,             -- Lưu list keyword dạng string
                    status TEXT DEFAULT 'NEW', -- NEW: Chưa AI xử lý, PROCESSED: Đã xong
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Tạo bảng reports
            c.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_content TEXT,    -- Nội dung bài viết final
                    sentiment_score REAL,   -- Điểm số (-10 đến 10)
                    trend TEXT,             -- Bullish/Bearish/Neutral
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
    except Exception as e:
        logger.error(f"Lỗi khởi tạo DB: {e}")

def check_article_exists(link: str) -> bool:
    """Kiểm tra link đã có trong DB chưa"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM articles WHERE id = ?", (link,))
            return c.fetchone() is not None
    except Exception:
        return False

def save_to_db(item: Dict[str, Any]) -> bool:
    """Lưu 1 bài báo vào DB"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            # Chuyển list keywords thành chuỗi JSON để lưu vào cột TEXT
            keywords_str = json.dumps(item["keywords"], ensure_ascii=False)
            
            c.execute('''
                INSERT OR IGNORE INTO articles (id, source, title, published, content, keywords, status)
                VALUES (?, ?, ?, ?, ?, ?, 'NEW')
            ''', (
                item["id"],
                item["source"],
                item["title"],
                item["published_at"],
                item["content"],
                keywords_str
            ))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Lỗi lưu DB bài viết {item.get('id')}: {e}")
        return False

# --- CÁC HÀM CRAWL/PARSE ---
def clean_html(raw_html: str) -> str:
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()

def check_keywords(text: str) -> List[str]:
    found_keywords = []
    text_lower = text.lower()
    all_keywords = KEYWORDS["DIRECT"] + KEYWORDS["CORRELATION"]
    for kw in all_keywords:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, text_lower):
            found_keywords.append(kw)
    return list(set(found_keywords)) # Loại bỏ keyword trùng lặp

def get_full_content(url: str) -> str:
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200: 
            return "Lỗi truy cập (Chặn Bot)"
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        if "kitco.com" in url:
            paragraphs = soup.select("div.article-body p")
        elif "investing.com" in url:
            paragraphs = soup.select("div.WYSIWYG p")
        else:
            paragraphs = soup.find_all('p')
            
        full_text = "\\n\\n".join([p.get_text().strip() for p in paragraphs])
        return full_text if len(full_text) > 200 else "Nội dung quá ngắn/bị ẩn."
    except Exception as e:
        return f"Lỗi cào dữ liệu: {e}"

def get_rss_feed_data(url: str):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        return feedparser.parse(response.content)
    except:
        return None

# --- HÀM CHÍNH ---
def get_gold_news():
    logger.info(">>> KHỞI TẠO DATABASE...")
    init_db() # 1. Tạo bảng nếu chưa có
    
    logger.info(">>> ĐANG QUÉT TIN TỨC...")
    now_utc = datetime.now(timezone.utc)
    time_limit = now_utc - timedelta(hours=24) 
    
    new_articles_count = 0

    for source in config.RSS_SOURCES:
        try:
            feed = get_rss_feed_data(source["url"])
            if not feed or not feed.entries:
                logger.warning(f"-> {source['name']}: Không lấy được dữ liệu.")
                continue

            logger.info(f"-> {source['name']}: Quét {len(feed.entries)} bài...")
            
            for entry in feed.entries:
                link = entry.get("link", "")
                
                # 2. KIỂM TRA TỒN TẠI TRƯỚC
                if check_article_exists(link):
                    continue

                # Xử lý ngày tháng
                published = entry.get("published", entry.get("updated", ""))
                if not published: continue
                try:
                    pub_date = parser.parse(published)
                    if pub_date.tzinfo is None: pub_date = pub_date.replace(tzinfo=timezone.utc)
                    if pub_date < time_limit: continue
                except: continue

                title = entry.get("title", "")
                summary = clean_html(entry.get("summary", ""))
                
                # Check Keyword
                matched_kws = check_keywords(title + " " + summary)
                
                if matched_kws:
                    logger.info(f"   [+] Tin mới: {title[:50]}...")
                    
                    full_content = get_full_content(link)
                    
                    news_item = {
                        "id": link,
                        "source": source["name"],
                        "published_at": pub_date.isoformat(),
                        "title": title,
                        "keywords": matched_kws,
                        "url": link,
                        "content": full_content
                    }
                    
                    # 3. LƯU VÀO DB
                    save_to_db(news_item)
                    new_articles_count += 1
                    time.sleep(1) # Delay nhẹ
            
        except Exception as e:
            logger.error(f"Lỗi nguồn {source['name']}: {e}")

    logger.info("="*60)
    logger.info(f"✅ HOÀN TẤT! Đã thêm {new_articles_count} bài viết mới vào Database.")
    logger.info("="*60)

if __name__ == "__main__":
    get_gold_news()

# --- HÀM PUBLIC CHO NGHIỆP VỤ KHÁC ---

def get_unprocessed_articles() -> List[Dict[str, Any]]:
    """Lấy tất cả bài viết có status = 'NEW'"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT id, source, title, content FROM articles WHERE status = 'NEW'")
            rows = c.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Lỗi lấy bài viết chưa xử lý: {e}")
        return []

def mark_articles_processed(ids: List[str]) -> None:
    """Chuyển status sang PROCESSED sau khi AI phân tích xong"""
    if not ids: return
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            placeholders = ','.join(['?'] * len(ids))
            sql = f"UPDATE articles SET status = 'PROCESSED' WHERE id IN ({placeholders})"
            c.execute(sql, ids)
            conn.commit()
    except Exception as e:
        logger.error(f"Lỗi cập nhật trạng thái bài viết: {e}")

def save_report(content: str, score: float, trend: str) -> None:
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO reports (report_content, sentiment_score, trend) VALUES (?, ?, ?)", 
                      (content, score, trend))
            conn.commit()
            logger.info("💾 Đã lưu báo cáo phân tích vào Database.")
    except Exception as e:
        logger.error(f"Lỗi lưu báo cáo: {e}")

def get_latest_report() -> Optional[Dict[str, Any]]:
    """Lấy báo cáo phân tích gần nhất để làm context"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT sentiment_score, trend, created_at FROM reports ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Lỗi lấy báo cáo mới nhất: {e}")
        return None