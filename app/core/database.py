import aiosqlite
from contextlib import asynccontextmanager
from typing import List, Dict, Optional, Any
import json
import logging
from datetime import datetime, timezone
from app.core import config 

logger = config.logger
DB_NAME = config.DB_NAME

@asynccontextmanager
async def get_db_connection():
    """Async Context manager để quản lý kết nối DB an toàn"""
    conn = None
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL;") 
            yield conn
    except Exception as e:
        logger.error(f"Lỗi kết nối CSDL (Async): {e}")
        raise e
    # aiosqlite context manager tự động close connection

async def init_db() -> None:
    """Khởi tạo bảng nếu chưa có (Async)"""
    try:
        async with get_db_connection() as conn:
            # Tạo bảng articles
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY,       -- Link bài viết là khóa chính
                    source TEXT,
                    title TEXT,
                    published TEXT,
                    content TEXT,              -- Nội dung full
                    keywords TEXT,             -- Lưu list keyword dạng string
                    status TEXT DEFAULT 'NEW', -- NEW: Chưa AI xử lý, PROCESSED: Đã xong
                    is_alerted INTEGER DEFAULT 0, -- 0: Chưa alert, 1: Đã alert (Breaking News)
                    image_url TEXT,            -- URL ảnh thumbnail
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Migration: Ensure columns exist (Ignore error if exists)
            try:
                await conn.execute("ALTER TABLE articles ADD COLUMN is_alerted INTEGER DEFAULT 0")
            except Exception: pass 
            try:
                await conn.execute("ALTER TABLE articles ADD COLUMN image_url TEXT")
            except Exception: pass

            # Tạo bảng reports
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_content TEXT,    -- Nội dung bài viết final
                    sentiment_score REAL,   -- Điểm số (-10 đến 10)
                    trend TEXT,             -- Bullish/Bearish/Neutral
                    signal_type TEXT,       -- BUY/SELL/WAIT (AI Signal)
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Migration for existing reports table
            try:
                await conn.execute("ALTER TABLE reports ADD COLUMN signal_type TEXT")
                await conn.execute("ALTER TABLE reports ADD COLUMN entry_price REAL")
                await conn.execute("ALTER TABLE reports ADD COLUMN stop_loss REAL")
                await conn.execute("ALTER TABLE reports ADD COLUMN take_profit REAL")
            except Exception: pass

            # Tạo bảng economic_events
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS economic_events (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    currency TEXT,
                    impact TEXT,
                    timestamp DATETIME,
                    forecast TEXT,
                    previous TEXT,
                    actual TEXT,
                    status TEXT DEFAULT 'pending'
                )
            ''')

            # Tạo bảng trade_signals
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS trade_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    signal_type TEXT, -- BUY/SELL/WAIT
                    source TEXT,      -- NEWS, AI_REPORT
                    score REAL,
                    is_processed INTEGER DEFAULT 0,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Migration: Add columns if not exists
            try:
                await conn.execute("ALTER TABLE trade_signals ADD COLUMN is_processed INTEGER DEFAULT 0")
            except Exception: pass
            try:
                await conn.execute("ALTER TABLE trade_signals ADD COLUMN entry_price REAL")
            except Exception: pass
            try:
                await conn.execute("ALTER TABLE trade_signals ADD COLUMN stop_loss REAL")
            except Exception: pass
            try:
                await conn.execute("ALTER TABLE trade_signals ADD COLUMN take_profit REAL")
            except Exception: pass
            
            # Tạo bảng trade_history
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS trade_history (
                    ticket INTEGER PRIMARY KEY,
                    signal_id INTEGER,
                    symbol TEXT,
                    order_type TEXT,
                    volume REAL,
                    open_price REAL,
                    sl REAL,
                    tp REAL,
                    close_price REAL,
                    profit REAL,
                    status TEXT DEFAULT 'OPEN',
                    strategy TEXT,    -- NEW: Strategy Name (NEWS, SNIPER, REPORT, CALENDAR)
                    close_reason TEXT, -- NEW: Reason for closing (HIT_SL, HIT_TP, MANUAL, etc.)
                    open_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    close_time TIMESTAMP,
                    FOREIGN KEY (signal_id) REFERENCES trade_signals(id)
                )
            ''')
            
            # Migration: Add columns if not exists
            try:
                await conn.execute("ALTER TABLE trade_history ADD COLUMN strategy TEXT")
            except Exception: pass
            
            try:
                await conn.execute("ALTER TABLE trade_history ADD COLUMN close_reason TEXT")
            except Exception: pass
            
            await conn.commit()
    except Exception as e:
        logger.error(f"Lỗi khởi tạo DB: {e}")

async def check_article_exists(link: str) -> bool:
    """Kiểm tra link đã có trong DB chưa"""
    try:
        async with get_db_connection() as conn:
            async with conn.execute("SELECT 1 FROM articles WHERE id = ?", (link,)) as cursor:
                result = await cursor.fetchone()
                return result is not None
    except Exception:
        return False

async def save_to_db(item: Dict[str, Any]) -> bool:
    """Lưu 1 bài báo vào DB"""
    try:
        async with get_db_connection() as conn:
            keywords_str = json.dumps(item["keywords"], ensure_ascii=False)
            
            await conn.execute('''
                INSERT OR IGNORE INTO articles (id, source, title, published, content, keywords, image_url, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW')
            ''', (
                item["id"],
                item["source"],
                item["title"],
                item["published_at"],
                item["content"],
                keywords_str,
                item.get("image_url")
            ))
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"Lỗi lưu DB bài viết {item.get('id')}: {e}")
        return False

async def get_unprocessed_articles() -> List[Dict[str, Any]]:
    """Lấy tất cả bài viết có status = 'NEW'"""
    try:
        async with get_db_connection() as conn:
            async with conn.execute("SELECT id, source, title, content FROM articles WHERE status = 'NEW'") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Lỗi lấy bài viết chưa xử lý: {e}")
        return []

async def mark_articles_processed(ids: List[str]) -> None:
    """Chuyển status sang PROCESSED sau khi AI phân tích xong"""
    if not ids: return
    try:
        async with get_db_connection() as conn:
            placeholders = ','.join(['?'] * len(ids))
            sql = f"UPDATE articles SET status = 'PROCESSED' WHERE id IN ({placeholders})"
            await conn.execute(sql, ids)
            await conn.commit()
    except Exception as e:
        logger.error(f"Lỗi cập nhật trạng thái bài viết: {e}")

async def save_report(content: str, score: float, trend: str, signal_data: Optional[Dict[str, Any]] = None) -> None:
    try:
        async with get_db_connection() as conn:
            sig_type = None
            entry = 0.0
            sl = 0.0
            tp = 0.0
            
            if signal_data:
                sig_type = signal_data.get('order_type')
                entry = signal_data.get('entry_price', 0.0)
                sl = signal_data.get('sl', 0.0)
                tp = signal_data.get('tp1', 0.0)
            
            await conn.execute('''
                INSERT INTO reports (report_content, sentiment_score, trend, signal_type, entry_price, stop_loss, take_profit) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (content, score, trend, sig_type, entry, sl, tp))
            
            await conn.commit()
            logger.info("💾 Đã lưu báo cáo phân tích vào Database (có Signal).")
    except Exception as e:
        logger.error(f"Lỗi lưu báo cáo: {e}")

async def get_latest_report() -> Optional[Dict[str, Any]]:
    """Lấy báo cáo phân tích gần nhất để làm context"""
    try:
        async with get_db_connection() as conn:
            async with conn.execute("SELECT * FROM reports ORDER BY id DESC LIMIT 1") as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Lỗi lấy báo cáo mới nhất: {e}")
        return None

async def get_unalerted_news(lookback_minutes: int = 30) -> List[Dict[str, Any]]:
    """Lấy tin chưa alert"""
    try:
        async with get_db_connection() as conn:
            async with conn.execute('''
                SELECT id, title, content, published, source, image_url
                FROM articles 
                WHERE is_alerted = 0 
                AND status = 'NEW'
                AND created_at >= datetime('now', ?)
                ORDER BY created_at DESC
            ''', (f'-{lookback_minutes} minutes',)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Lỗi lấy tin chưa alert: {e}")
        return []

async def mark_article_alerted(id: str) -> None:
    try:
        async with get_db_connection() as conn:
            await conn.execute("UPDATE articles SET is_alerted = 1 WHERE id = ?", (id,))
            await conn.commit()
    except Exception as e:
        logger.error(f"Lỗi đánh dấu alert: {e}")

# --- Economic Calendar Database Methods (Async) ---
async def upsert_economic_event(event: Dict[str, Any]) -> bool:
    try:
        async with get_db_connection() as conn:
            await conn.execute('''
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
                event["timestamp"],
                event["forecast"],
                event["previous"],
                event["actual"]
            ))
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"Lỗi upsert economic event {event.get('id')}: {e}")
        return False

async def get_pending_pre_alerts(minutes_window: int = 60) -> List[Dict[str, Any]]:
    try:
        async with get_db_connection() as conn:
            async with conn.execute('''
                SELECT * FROM economic_events
                WHERE timestamp > datetime('now') 
                AND timestamp <= datetime('now', ?)
                AND status = 'pending'
                AND impact = 'High'
            ''', (f'+{minutes_window} minutes',)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Lỗi get pre-alerts: {e}")
        return []

async def get_pending_post_alerts() -> List[Dict[str, Any]]:
    try:
        async with get_db_connection() as conn:
            async with conn.execute('''
                SELECT * FROM economic_events
                WHERE actual IS NOT NULL 
                AND actual != '' 
                AND status != 'post_notified'
                AND impact = 'High'
            ''') as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Lỗi get post-alerts: {e}")
        return []

async def update_event_status(event_id: str, new_status: str) -> None:
    try:
        async with get_db_connection() as conn:
            await conn.execute("UPDATE economic_events SET status = ? WHERE id = ?", (new_status, event_id))
            await conn.commit()
    except Exception as e:
        logger.error(f"Lỗi update status event {event_id}: {e}")

async def get_incomplete_events_today() -> List[Dict[str, Any]]:
    try:
        async with get_db_connection() as conn:
            async with conn.execute('''
                SELECT * FROM economic_events
                WHERE date(timestamp) = date('now', 'localtime') 
                AND (actual IS NULL OR actual = '')
            ''') as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Lỗi get incomplete events: {e}")
        return []

async def check_upcoming_high_impact_news(minutes: int = 30) -> Optional[str]:
    try:
        async with get_db_connection() as conn:
            async with conn.execute('''
                SELECT title FROM economic_events
                WHERE impact = 'High'
                AND timestamp > datetime('now')
                AND timestamp <= datetime('now', ?)
            ''', (f'+{minutes} minutes',)) as cursor:
                row = await cursor.fetchone()
                return row['title'] if row else None
    except Exception as e:
        logger.error(f"Lỗi check upcoming news: {e}")
        return None

async def check_recent_high_impact_news(minutes: int = 15) -> Optional[str]:
    try:
        async with get_db_connection() as conn:
            async with conn.execute('''
                SELECT title FROM economic_events
                WHERE impact = 'High'
                AND timestamp <= datetime('now')
                AND timestamp >= datetime('now', ?)
            ''', (f'-{minutes} minutes',)) as cursor:
                row = await cursor.fetchone()
                return row['title'] if row else None
    except Exception as e:
        logger.error(f"Lỗi check recent news: {e}")
        return None

async def save_trade_signal(symbol: str, signal_type: str, source: str, score: float, entry: float = None, sl: float = None, tp: float = None) -> bool:
    try:
        async with get_db_connection() as conn:
            await conn.execute('''
                INSERT INTO trade_signals (symbol, signal_type, source, score, entry_price, stop_loss, take_profit)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (symbol, signal_type, source, score, entry, sl, tp))
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"Lỗi save_trade_signal: {e}")
        return False

async def get_latest_valid_signal(symbol: str, ttl_minutes: int = 60) -> Optional[Dict[str, Any]]:
    try:
        async with get_db_connection() as conn:
            # 1. News
            async with conn.execute('''
                SELECT * FROM trade_signals
                WHERE symbol = ? 
                AND source = 'NEWS'
                AND is_processed = 0
                AND created_at >= datetime('now', ?)
                ORDER BY created_at DESC
                LIMIT 1
            ''', (symbol, f'-{ttl_minutes} minutes')) as cursor:
                news_signal = await cursor.fetchone()
                if news_signal: return dict(news_signal)
            
            # 2. AI Report
            async with conn.execute('''
                SELECT * FROM trade_signals
                WHERE symbol = ? 
                AND source = 'AI_REPORT'
                AND is_processed = 0
                AND created_at >= datetime('now', ?)
                ORDER BY created_at DESC
                LIMIT 1
            ''', (symbol, f'-{ttl_minutes} minutes')) as cursor:
                ai_signal = await cursor.fetchone()
                if ai_signal: return dict(ai_signal)
                
            return None
    except Exception as e:
        logger.error(f"Lỗi get_latest_valid_signal: {e}")
        return None

async def mark_signal_processed(signal_id: int) -> bool:
    """
    Đánh dấu signal đã được xử lý (processed) để tránh duplicate execution.
    """
    try:
        async with get_db_connection() as conn:
            await conn.execute("UPDATE trade_signals SET is_processed = 1 WHERE id = ?", (signal_id,))
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"Lỗi mark_signal_processed: {e}")
        return False

async def get_all_valid_signals(symbol: str, ttl_minutes: int = 60) -> List[Dict[str, Any]]:
    """
    Lấy TẤT CẢ các tín hiệu chưa xử lý (is_processed = 0) từ NEWS và AI_REPORT.
    Sắp xếp: Ưu tiên chất lượng (ABS score) trước, thời gian sau.
    Input: symbol (str), ttl_minutes (int).
    Output: List[Dict].
    """
    try:
        async with get_db_connection() as conn:
            async with conn.execute('''
                SELECT * FROM trade_signals
                WHERE symbol = ? 
                AND is_processed = 0
                AND source IN ('NEWS', 'AI_REPORT')
                AND created_at >= datetime('now', ?)
                ORDER BY ABS(score) DESC, created_at DESC
            ''', (symbol, f'-{ttl_minutes} minutes')) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Lỗi get_all_valid_signals: {e}")
        return []

async def get_events_for_trap(min_minutes: float = 1.6, max_minutes: float = 2.4) -> List[Dict[str, Any]]:
    """
    Lấy các tin USD High Impact sắp ra trong khoảng [min, max] phút tới.
    Mục đích: Trap Trading (Straddle).
    """
    try:
        async with get_db_connection() as conn:
            # SQLite datetime('now') is UTC.
            # Convert minutes to fraction of day for arithmetic if needed, or use modifier
            # Modifier format: '+2 minutes'
            
            # Since we need a range, we check:
            # timestamp >= now + min_minutes
            # timestamp <= now + max_minutes
            
            min_offset = f'+{min_minutes} minutes'
            max_offset = f'+{max_minutes} minutes'
            
            # Debug SQL logic: 
            # timestamp between (now + 1.5 min) and (now + 2.5 min)
            
            async with conn.execute('''
                SELECT * FROM economic_events
                WHERE currency = 'USD'
                AND impact = 'High'
                AND status = 'pre_notified'
                AND timestamp >= datetime('now', ?)
                AND timestamp <= datetime('now', ?)
            ''', (min_offset, max_offset)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Lỗi get_events_for_trap: {e}")
        return []

# --- Trade History Database Methods (Async) ---
async def save_trade_entry(ticket: int, signal_id: Optional[int], symbol: str, order_type: str, 
                           volume: float, open_price: float, sl: float, tp: float, strategy: str = 'MANUAL') -> bool:
    """
    Lưu trade mới vào database khi order được thực thi thành công.
    Status mặc định là 'OPEN'.
    Strategy: NEWS, SNIPER, REPORT, CALENDAR or MANUAL.
    """
    try:
        async with get_db_connection() as conn:
            await conn.execute('''
                INSERT INTO trade_history (ticket, signal_id, symbol, order_type, volume, 
                                          open_price, sl, tp, strategy, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
            ''', (ticket, signal_id, symbol, order_type, volume, open_price, sl, tp, strategy))
            await conn.commit()
            logger.info(f"💾 Saved trade to DB: Ticket #{ticket} ({order_type} {symbol})")
            return True
    except Exception as e:
        logger.error(f"❌ Lỗi save_trade_entry: {e}")
        return False

async def get_open_trades() -> List[Dict[str, Any]]:
    """
    Lấy tất cả các trade đang mở (status='OPEN')
    """
    try:
        async with get_db_connection() as conn:
            async with conn.execute('''
                SELECT * FROM trade_history WHERE status = 'OPEN'
            ''') as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Lỗi get_open_trades: {e}")
        return []

async def update_trade_exit(ticket: int, close_price: float, profit: float, status: str = 'CLOSED', close_reason: str = None, sl: float = None, tp: float = None, close_time: Any = None) -> bool:
    """
    Cập nhật thông tin khi trade đóng.
    Thêm close_reason và SL/TP.
    close_time: Có thể là int (timestamp) hoặc string.
    """
    try:
        async with get_db_connection() as conn:
            # ... (Phần khai báo SQL update giữ nguyên) ...
            sql = '''
                UPDATE trade_history 
                SET close_price = ?, profit = ?, status = ?, close_reason = ?
            '''
            params = [close_price, profit, status, close_reason]
            
            # --- XỬ LÝ TIME UTC ---
            if close_time is not None:
                # Chuyển Timestamp sang UTC String
                if isinstance(close_time, (int, float)):
                    utc_time = datetime.fromtimestamp(close_time, tz=timezone.utc)
                    val = utc_time.strftime('%Y-%m-%d %H:%M:%S')
                    
                    sql += ", close_time = ?"
                    params.append(val)
                else:
                    # Trường hợp đã là string
                    sql += ", close_time = ?"
                    params.append(close_time)
            else:
                # Fallback: Dùng giờ hiện tại của DB (thường là UTC nếu config đúng, hoặc Local)
                # Tốt nhất nên dùng datetime.now(timezone.utc) từ Python luôn để đồng bộ
                now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                sql += ", close_time = ?"
                params.append(now_utc)
                
            # ... (Phần xử lý SL/TP giữ nguyên) ...
            if sl is not None:
                sql += ", sl = ?"
                params.append(sl)
            
            if tp is not None:
                sql += ", tp = ?"
                params.append(tp)
            
            # CHỐT CÂU LỆNH WHERE
            sql += " WHERE ticket = ?"
            params.append(ticket)
            
            await conn.execute(sql, tuple(params))
            await conn.commit()
            logger.info(f"💾 Updated trade exit: Ticket #{ticket} (Profit: {profit:.2f})")
            return True
    except Exception as e:
        logger.error(f"❌ Lỗi update_trade_exit: {e}")
        return False

async def update_trade_profit(ticket: int, profit: float) -> bool:
    """
    Cập nhật floating profit cho trade đang mở.
    """
    try:
        async with get_db_connection() as conn:
            await conn.execute('''
                UPDATE trade_history SET profit = ? WHERE ticket = ?
            ''', (profit, ticket))
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"❌ Lỗi update_trade_profit: {e}")
        return False

async def update_trade_entry_price(ticket: int, open_price: float) -> bool:
    """
    Make update_trade_entry_price compatible alias for update_trade_details just for price.
    """
    return await update_trade_details(ticket, open_price, 0.0, 0.0)

async def update_trade_details(ticket: int, open_price: float, sl: float, tp: float) -> bool:
    """
    Cập nhật chi tiết Open Price, SL, TP từ MT5 (fix lỗi Points vs Price).
    Nếu SL/TP = 0 thì có thể giữ nguyên hoặc update tùy logic, ở đây ta update luôn.
    """
    try:
        async with get_db_connection() as conn:
            # Chỉ update nếu giá trị > 0 để tránh ghi đè sai nếu không cần thiết, 
            # nhưng yêu cầu là đồng bộ chính xác từ MT5 nên ta update thẳng.
            # Tuy nhiên, SQL dynamic sẽ tốt hơn nếu data thiếu. 
            # Ở đây giả sử trading_monitor luôn truyền full data.
            
            await conn.execute('''
                UPDATE trade_history 
                SET open_price = ?, sl = ?, tp = ?
                WHERE ticket = ?
            ''', (open_price, sl, tp, ticket))
            
            await conn.commit()
            logger.info(f"💾 Updated trade details #{ticket}: Price={open_price}, SL={sl}, TP={tp}")
            return True
    except Exception as e:
        logger.error(f"❌ Lỗi update_trade_details: {e}")
        return False

async def get_trade_metadata(ticket: int) -> Optional[Dict[str, Any]]:
    """
    Lấy metadata của trade từ signal (JOIN với trade_signals).
    Trả về {'source': str, 'score': float} nếu có signal_id.
    Trả về None nếu signal_id là NULL (Sniper/Straddle/Manual).
    """
    try:
        async with get_db_connection() as conn:
            async with conn.execute('''
                SELECT ts.source, ts.score
                FROM trade_history th
                LEFT JOIN trade_signals ts ON th.signal_id = ts.id
                WHERE th.ticket = ?
            ''', (ticket,)) as cursor:
                row = await cursor.fetchone()
                
                if not row:
                    logger.warning(f"Trade #{ticket} not found in database")
                    return None
                
                # If signal_id was NULL, the JOIN will return NULL for source/score
                if row['source'] is None:
                    return None  # No signal metadata (Sniper/Straddle/Manual)
                
                return {
                    'source': row['source'],
                    'score': row['score'] if row['score'] is not None else 0.0
                }
    except Exception as e:
        logger.error(f"❌ Lỗi get_trade_metadata for ticket {ticket}: {e}.")
        return None
