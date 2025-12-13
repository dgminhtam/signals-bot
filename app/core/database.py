import sqlite3
from contextlib import contextmanager
from typing import List, Dict, Optional, Any
import json
import logging
from app.core import config # Updated import

logger = config.logger
DB_NAME = config.DB_NAME

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
                    is_alerted INTEGER DEFAULT 0, -- 0: Chưa alert, 1: Đã alert (Breaking News)
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Migration: Ensure is_alerted column exists (for existing DB)
            try:
                c.execute("ALTER TABLE articles ADD COLUMN is_alerted INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass # Column already exists

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

            # Tạo bảng economic_events (MỚI)
            c.execute('''
                CREATE TABLE IF NOT EXISTS economic_events (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    currency TEXT,
                    impact TEXT,
                    timestamp DATETIME,
                    forecast TEXT,
                    previous TEXT,
                    actual TEXT,
                    status TEXT DEFAULT 'pending'  -- pending, pre_notified, post_notified
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

def get_unalerted_news(lookback_minutes: int = 30) -> List[Dict[str, Any]]:
    """
    Lấy các bài viết MỚI trong khoảng thời gian gầy đây (lookback_minutes) 
    mà CHƯA được gửi Alert (is_alerted = 0).
    """
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            # SQLite dùng strftime để tính thời gian
            # 'now', f'-{lookback_minutes} minutes'
            
            c.execute('''
                SELECT id, title, content, published, source 
                FROM articles 
                WHERE is_alerted = 0 
                AND created_at >= datetime('now', ?)
                ORDER BY created_at DESC
            ''', (f'-{lookback_minutes} minutes',))
            
            rows = c.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Lỗi lấy tin chưa alert: {e}")
        return []

def mark_article_alerted(id: str) -> None:
    """Đánh dấu bài viết đã được gửi Alert"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE articles SET is_alerted = 1 WHERE id = ?", (id,))
            conn.commit()
    except Exception as e:
        logger.error(f"Lỗi đánh dấu alert: {e}")

# --- Economic Calendar Database Methods ---
def upsert_economic_event(event: Dict[str, Any]) -> bool:
    """Insert hoặc Update sự kiện kinh tế"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO economic_events (id, title, currency, impact, timestamp, forecast, previous, actual)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    actual = excluded.actual,
                    forecast = excluded.forecast,
                    timestamp = excluded.timestamp
            ''', (
                event["id"],
                event["event"],
                event["currency"],
                event["impact"],
                event["timestamp"], # Requires datetime object or ISO string in event dict
                event["forecast"],
                event["previous"],
                event["actual"]
            ))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Lỗi upsert economic event {event.get('id')}: {e}")
        return False

def get_pending_pre_alerts(minutes_window: int = 60) -> List[Dict[str, Any]]:
    """Lấy sự kiện sắp diễn ra để gửi Pre-Alert"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            # Lấy sự kiện trong tương lai gần (0 đến minutes_window phút)
            # VÀ chưa gửi alert (status != 'pre_notified' AND status != 'post_notified')
            # Lưu ý timestamp phải là string ISO format chuẩn để so sánh
            c.execute('''
                SELECT * FROM economic_events
                WHERE timestamp > datetime('now') 
                AND timestamp <= datetime('now', ?)
                AND status = 'pending'
            ''', (f'+{minutes_window} minutes',))
            return [dict(row) for row in c.fetchall()]
    except Exception as e:
        logger.error(f"Lỗi get pre-alerts: {e}")
        return []

def get_pending_post_alerts() -> List[Dict[str, Any]]:
    """Lấy sự kiện ĐÃ CÓ Actual nhưng chưa gửi Post-Alert (Status != post_notified)"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            # Actual khác rỗng và chưa notified post
            c.execute('''
                SELECT * FROM economic_events
                WHERE actual IS NOT NULL 
                AND actual != '' 
                AND status != 'post_notified'
            ''')
            return [dict(row) for row in c.fetchall()]
    except Exception as e:
        logger.error(f"Lỗi get post-alerts: {e}")
        return []

def update_event_status(event_id: str, new_status: str) -> None:
    """Cập nhật trạng thái notify"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE economic_events SET status = ? WHERE id = ?", (new_status, event_id))
            conn.commit()
    except Exception as e:
        logger.error(f"Lỗi update status event {event_id}: {e}")

def get_incomplete_events_today() -> List[Dict[str, Any]]:
    """Lấy các sự kiện hôm nay mà chưa có số liệu Actual (để quyết định fetch lại)"""
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            # Lấy các sự kiện mà timestamp là hôm nay VÀ actual chưa có
            # Dùng date(timestamp) so với date('now', 'localtime')
            c.execute('''
                SELECT * FROM economic_events
                WHERE date(timestamp) = date('now', 'localtime') 
                AND (actual IS NULL OR actual = '')
            ''')
            return [dict(row) for row in c.fetchall()]
    except Exception as e:
        logger.error(f"Lỗi get incomplete events: {e}")
        return []
