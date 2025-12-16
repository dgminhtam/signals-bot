import time
import html
import json
import os
from typing import List, Dict, Optional
import logging
from datetime import datetime, timedelta
from curl_cffi import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from dateutil import tz
from app.core import config
from app.core import database
from app.services import telegram_bot
from app.services import ai_engine

logger = config.logger

SCHEDULE_JSON_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CACHE_FILE = "data/ff_schedule.json"
CACHE_TTL = 3600  # 60 minutes

class EconomicCalendarService:
    def __init__(self):
        self.base_url = "https://www.forexfactory.com/calendar"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.5"
        }
        if not os.path.exists("data"):
            os.makedirs("data")

    def fetch_schedule_json(self) -> List[Dict]:
        """
        Lấy lịch sự kiện từ JSON API (High Performance).
        Cache kết quả để giảm tải.
        """
        try:
            # 1. Check Cache
            if os.path.exists(CACHE_FILE):
                mod_time = os.path.getmtime(CACHE_FILE)
                if time.time() - mod_time < CACHE_TTL:
                    with open(CACHE_FILE, 'r') as f:
                        logger.info("📦 Loading schedule from cache...")
                        return json.load(f)
            
            # 2. Fetch from URL
            logger.info(f"🌐 Fetching Schedule JSON: {SCHEDULE_JSON_URL}")
            response = requests.get(SCHEDULE_JSON_URL, impersonate="chrome120", timeout=30)
            if response.status_code == 200:
                data = response.json()
                with open(CACHE_FILE, 'w') as f:
                    json.dump(data, f)
                return data
            else:
                logger.error(f"❌ Failed to fetch schedule JSON. Status: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Error fetching schedule JSON: {e}")
            return []

    def sync_schedule_to_db(self):
        """
        Đồng bộ lịch từ JSON vào DB.
        Cơ chế: MERGE & PRESERVE STATUS
        1. Tìm bản ghi cũ (dựa trên Title + Currency + Date) để lấy Status cũ (tránh bắn lại Alert).
        2. Xóa tất cả phiên bản cũ của sự kiện này.
        3. Insert sự kiện mới (với ID mới theo giờ mới) nhưng giữ nguyên Status cũ.
        """
        events = self.fetch_schedule_json()
        count = 0
        
        # Mở connection 1 lần cho hiệu suất
        with database.get_db_connection() as conn:
            c = conn.cursor()
            
            for item in events:
                try:
                    title = item.get('title', 'Unknown')
                    currency = item.get('country', 'USD')
                    impact = item.get('impact', 'Low')
                    date_str = item.get('date') # Format: 2024-01-24T08:15:00-05:00
                    
                    # 1. Parse DateTime & Convert to UTC
                    dt = date_parser.parse(date_str)
                    dt_utc = dt.astimezone(tz.UTC)
                    timestamp_iso = dt_utc.strftime('%Y-%m-%d %H:%M:%S')
                    date_only = dt_utc.strftime('%Y-%m-%d') # Lấy ngày YYYY-MM-DD
                    
                    # 2. Generate Deterministic ID
                    id_str = f"{timestamp_iso}_{currency}_{title}".replace(" ", "_").replace("/", "").replace(":", "")
                    
                    # --- BẮT ĐẦU LOGIC MERGE ---
                    
                    # Bước 1: Tìm Status cũ
                    c.execute('''
                        SELECT status FROM economic_events
                        WHERE title = ? 
                        AND currency = ? 
                        AND date(timestamp) = ?
                    ''', (title, currency, date_only))
                    
                    rows = c.fetchall()
                    existing_status = 'pending'
                    
                    for r in rows:
                        s = r['status']
                        if s in ['pre_notified', 'post_notified']:
                            existing_status = s
                            break 
                            
                    # Bước 2: Dọn dẹp bản ghi cũ (Duplicate Cleanup)
                    c.execute('''
                        DELETE FROM economic_events 
                        WHERE title = ? 
                        AND currency = ? 
                        AND date(timestamp) = ?
                    ''', (title, currency, date_only))
                    
                    if c.rowcount > 0 and existing_status != 'pending':
                         logger.info(f"♻️ Merged event '{title}' (Preserved status: {existing_status})")

                    # Bước 3: Insert bản ghi mới với Status bảo toàn
                    c.execute('''
                        INSERT INTO economic_events (id, title, currency, impact, timestamp, forecast, previous, actual, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        id_str, title, currency, impact, timestamp_iso, 
                        item.get('forecast', ''), 
                        item.get('previous', ''), 
                        "", # Actual is empty in schedule
                        existing_status
                    ))
                    count += 1
                    
                except Exception as e:
                    logger.warning(f"Skipping JSON item: {e}")
                    continue
            
            conn.commit()
                
        logger.info(f"✅ Synced {count} events from JSON Schedule (Merge & Preserve Status).")

    def fetch_realtime_results_html(self):
        """
        Quét HTML để lấy kết quả Actual Real-time.
        Logic update thông minh: Match theo Title + Currency + Date (bỏ qua Time ID).
        Safe Extraction: Kiểm tra thẻ tồn tại để tránh crash.
        """
        url = f"{self.base_url}?day=today"
        logger.info(f"⚡ scanning Real-time HTML: {url}")
        
        try:
            response = requests.get(url, headers=self.headers, impersonate="chrome120", timeout=30)
            if response.status_code != 200: return

            soup = BeautifulSoup(response.content, "html.parser")
            table = soup.find("table", class_="calendar__table")
            if not table: return
            
            rows = table.find_all("tr", class_="calendar__row")
            current_date_str = ""
            
            # Mở DB connection
            with database.get_db_connection() as conn:
                c = conn.cursor()
                
                for row in rows:
                    try:
                        # 1. Safe Date Extraction
                        if "calendar__row--new-day" in row.get("class", []):
                            d_tag = row.find("span", class_="date")
                            if d_tag: 
                                current_date_str = d_tag.text.strip()
                        
                        # 2. Safe Field Extraction
                        title_tag = row.find("span", class_="calendar__event-title")
                        currency_tag = row.find("td", class_="calendar__currency")
                        actual_tag = row.find("td", class_="calendar__actual")
                        time_tag = row.find("td", class_="calendar__time")
                        
                        # Skip if critical info missing
                        if not title_tag or not currency_tag or not actual_tag:
                            continue

                        title = title_tag.text.strip()
                        currency = currency_tag.text.strip()
                        actual = actual_tag.text.strip()
                        
                        # Only process if Actual value exists
                        if not actual: continue

                        # Parse Date
                        result_time = time_tag.text.strip() if time_tag else ""
                        dt_utc = self.parse_datetime_html(current_date_str, result_time)
                        
                        if not dt_utc: continue
                        
                        date_only = dt_utc.strftime('%Y-%m-%d')
                        
                        # --- LOGIC UPDATE ACTUAL ---
                        c.execute('''
                            UPDATE economic_events 
                            SET actual = ? 
                            WHERE title = ? 
                            AND currency = ? 
                            AND date(timestamp) = ?
                            AND (actual IS NULL OR actual = '')
                        ''', (actual, title, currency, date_only))
                        
                        if c.rowcount > 0:
                            logger.info(f"✅ Updated Actual for {title}: {actual}")
                            
                    except Exception as row_error:
                        logger.warning(f"⚠️ Error parsing row: {row_error}")
                        continue
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"❌ Error scanning HTML: {e}")

    def parse_datetime_html(self, date_str, time_str):
        """Helper để parse time từ HTML ForexFactory (New York Time) về UTC"""
        try:
            if not date_str or not time_str: return None
            # Fix date format variations if needed
            clean_date = " ".join(date_str.split()[1:]) if len(date_str.split()) > 1 else date_str
            full_str = f"{clean_date} {datetime.now().year} {time_str}"
            dt_naive = date_parser.parse(full_str)
            ny_tz = tz.gettz('America/New_York')
            dt_ny = dt_naive.replace(tzinfo=ny_tz)
            return dt_ny.astimezone(tz.UTC)
        except: return None

    def process_calendar_alerts(self):
        try:
            self.sync_schedule_to_db()
            
            incomplete = database.get_incomplete_events_today()
            if incomplete:
                self.fetch_realtime_results_html()
            
            now_utc = datetime.now(tz.UTC)
            
            # Pre-Alerts
            pre_alerts = database.get_pending_pre_alerts(60)
            for event in pre_alerts:
                ts = date_parser.parse(event['timestamp']) # UTC string from DB
                if ts.tzinfo is None: ts = ts.replace(tzinfo=tz.UTC)
                diff = (ts - now_utc).total_seconds() / 60
                
                # Convert UTC to VN Time for display
                vn_tz = tz.gettz('Asia/Ho_Chi_Minh')
                ts_vn = ts.astimezone(vn_tz)
                time_str = ts_vn.strftime('%H:%M')
                
                self.send_pre_alert(event, int(diff), time_str)
                database.update_event_status(event['id'], 'pre_notified')
                
            # Post-Alerts
            post_alerts = database.get_pending_post_alerts()
            for event in post_alerts:
                ts = date_parser.parse(event['timestamp']) # UTC string
                if ts.tzinfo is None: ts = ts.replace(tzinfo=tz.UTC)
                
                vn_tz = tz.gettz('Asia/Ho_Chi_Minh')
                ts_vn = ts.astimezone(vn_tz)
                time_str = ts_vn.strftime('%H:%M')
                
                self.send_post_alert(event, time_str)
                database.update_event_status(event['id'], 'post_notified')

        except Exception as e:
            logger.error(f"Error in hybrid process: {e}")

    def send_pre_alert(self, event, minutes_left, time_str):
        analysis = ai_engine.analyze_pre_economic_data(event)
        
        # Translate Label: Forecast/Previous -> Dự báo/Kỳ trước
        forecast_val = event['forecast'] if event['forecast'] else "N/A"
        prev_val = event['previous'] if event['previous'] else "N/A"

        if analysis:
            exp = html.escape(analysis.get('explanation', ''))
            high = html.escape(analysis.get('scenario_high', ''))
            low = html.escape(analysis.get('scenario_low', ''))
            msg = (f"📢 <b>BẢN TIN CHUẨN BỊ (Trước {minutes_left}p)</b>\n\n"
                   f"🔥 <b>SẮP CÓ TIN MẠNH ({time_str}): {event['title']}</b>\n"
                   f"⚠️ Cặp tiền: {event['currency']} Pairs\n"
                   f"📊 Dữ liệu: Dự báo {forecast_val} (Kỳ trước {prev_val})\n\n"
                   f"💡 <b>Phân tích:</b> {exp}\n\n"
                   f"↗️ <b>{high}</b>\n"
                   f"↘️ <b>{low}</b>\n\n"
                   f"#PreNews")
        else:
            msg = (f"📢 <b>BẢN TIN CHUẨN BỊ (Trước {minutes_left}p)</b>\n\n"
                   f"🔥 <b>SẮP CÓ TIN MẠNH ({time_str}): {event['title']}</b>\n"
                   f"⚠️ Cặp tiền: {event['currency']} Pairs\n"
                   f"📊 Dữ liệu: Dự báo {forecast_val} (Kỳ trước {prev_val})\n\n"
                   f"#PreNews")
        telegram_bot.send_message(msg)
        
    def send_post_alert(self, event, time_str):
        analysis = ai_engine.analyze_economic_data(event)
        
        actual_val = event['actual']
        forecast_val = event['forecast'] if event['forecast'] else "N/A"
        prev_val = event['previous'] if event['previous'] else "N/A"
        
        if analysis:
            score = analysis['sentiment_score']
            icon = "🟢" if score > 0 else "🔴" if score < 0 else "🟡"
            clean_analysis = html.escape(analysis['impact_analysis'])
            
            # New Localized Format
            msg = (f"📢 <b>BẢN TIN KẾT QUẢ</b>\n"
                   f"⚡ Tin: <b>{event['title']}</b>\n"
                   f"--------------------\n"
                   f"🔢 Thực tế:  <b>{actual_val}</b> {icon}\n"
                   f"   Dự báo:   {forecast_val}\n"
                   f"   Kỳ trước: {prev_val}\n"
                   f"--------------------\n"
                   f"👉 <b>Đánh giá:</b> {score}/10 ({analysis['conclusion']})\n"
                   f"📉 <b>Phân tích:</b> {clean_analysis}\n\n"
                   f"#EconomicResult")
        else:
            msg = (f"📢 <b>BẢN TIN KẾT QUẢ</b>\n"
                   f"⚡ Tin: <b>{event['title']}</b>\n"
                   f"--------------------\n"
                   f"🔢 Thực tế:  <b>{actual_val}</b>\n"
                   f"   Dự báo:   {forecast_val}\n"
                   f"   Kỳ trước: {prev_val}\n"
                   f"#EconomicResult")
        telegram_bot.send_message(msg)
