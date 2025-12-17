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
        """Lấy lịch sự kiện từ JSON API."""
        try:
            if os.path.exists(CACHE_FILE):
                mod_time = os.path.getmtime(CACHE_FILE)
                if time.time() - mod_time < CACHE_TTL:
                    with open(CACHE_FILE, 'r') as f:
                        return json.load(f)
            
            logger.info(f"🌐 Fetching Schedule JSON: {SCHEDULE_JSON_URL}")
            response = requests.get(SCHEDULE_JSON_URL, impersonate="chrome120", timeout=30)
            if response.status_code == 200:
                data = response.json()
                with open(CACHE_FILE, 'w') as f:
                    json.dump(data, f)
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching schedule JSON: {e}")
            return []

    def sync_schedule_to_db(self):
        """
        Đồng bộ lịch từ JSON vào DB.
        Sử dụng logic FUZZY DELETE (±1 ngày) để dọn dẹp các tin trùng lặp.
        """
        events = self.fetch_schedule_json()
        if not events: return

        count = 0
        with database.get_db_connection() as conn:
            c = conn.cursor()
            
            for item in events:
                try:
                    title = item.get('title', 'Unknown')
                    currency = item.get('country', 'USD')
                    impact = item.get('impact', 'Low')
                    
                    if impact not in ['High', 'Medium']: continue

                    # JSON gốc luôn có timezone, dateutil tự hiểu và đổi về UTC chuẩn
                    date_str = item.get('date')
                    dt = date_parser.parse(date_str)
                    dt_utc = dt.astimezone(tz.UTC)
                    timestamp_iso = dt_utc.strftime('%Y-%m-%d %H:%M:%S')
                    date_only = dt_utc.strftime('%Y-%m-%d')
                    
                    # ID Deterministic
                    safe_title = title.replace(" ", "_").replace("/", "").replace(":", "")
                    id_str = f"{timestamp_iso}_{currency}_{safe_title}"
                    
                    # 1. Tìm Status cũ (để bảo lưu trạng thái đã báo)
                    c.execute('''
                        SELECT status FROM economic_events
                        WHERE title = ? 
                        AND currency = ? 
                        AND date(timestamp) BETWEEN date(?, '-1 day') AND date(?, '+1 day')
                    ''', (title, currency, date_only))
                    
                    rows = c.fetchall()
                    existing_status = 'pending'
                    for r in rows:
                        if r['status'] in ['pre_notified', 'post_notified']:
                            existing_status = r['status']
                            break
                    
                    # 2. Xóa sạch bản ghi cũ trong vùng ±1 ngày
                    c.execute('''
                        DELETE FROM economic_events 
                        WHERE title = ? 
                        AND currency = ? 
                        AND date(timestamp) BETWEEN date(?, '-1 day') AND date(?, '+1 day')
                    ''', (title, currency, date_only))

                    # 3. Insert bản ghi chuẩn
                    c.execute('''
                        INSERT INTO economic_events (id, title, currency, impact, timestamp, forecast, previous, actual, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        id_str, title, currency, impact, timestamp_iso, 
                        item.get('forecast', ''), 
                        item.get('previous', ''), 
                        "", existing_status
                    ))
                    count += 1
                except Exception: continue
            
            conn.commit()
        logger.info(f"✅ Synced {count} High/Medium events to DB.")

    def fetch_realtime_results_html(self):
        """
        Quét HTML để lấy kết quả Actual.
        URL: Quét toàn bộ tuần (Mặc định của ForexFactory).
        Logic: Exact UTC Match (Server VN -> UTC Conversion).
        """
        # Không cần tham số ?day=... để lấy mặc định cả tuần
        url = self.base_url 
        logger.info(f"⚡ Scanning Real-time HTML (Weekly View): {url}")
        
        try:
            response = requests.get(url, headers=self.headers, impersonate="chrome120", timeout=30)
            if response.status_code != 200: return

            soup = BeautifulSoup(response.content, "html.parser")
            table = soup.find("table", class_="calendar__table")
            if not table: return
            
            rows = table.find_all("tr", class_="calendar__row")
            current_date_str = ""
            last_time_str = ""
            
            with database.get_db_connection() as conn:
                c = conn.cursor()
                
                for row in rows:
                    try:
                        # 1. Lấy ngày (Header)
                        if "calendar__row--new-day" in row.get("class", []):
                            d_tag = row.find("span", class_="date")
                            if d_tag:
                                # Clean: "Tue Dec 16 Oct Data" -> "Tue Dec 16"
                                current_date_str = " ".join(d_tag.text.strip().split()[:3])
                                last_time_str = ""
                        
                        if "data-event-id" not in row.attrs: continue

                        # 2. Lấy thông tin
                        title_tag = row.find("span", class_="calendar__event-title")
                        currency_tag = row.find("td", class_="calendar__currency")
                        actual_tag = row.find("td", class_="calendar__actual")
                        
                        if not title_tag or not currency_tag or not actual_tag: continue

                        title = title_tag.text.strip()
                        currency = currency_tag.text.strip()
                        actual = actual_tag.text.strip()
                        
                        if not actual: continue

                        # 3. Lấy giờ (Time)
                        time_tag = row.find("td", class_="calendar__time")
                        result_time = time_tag.text.strip() if time_tag else ""
                        
                        if result_time:
                            last_time_str = result_time
                        elif last_time_str:
                            result_time = last_time_str

                        # 4. QUY ĐỔI MÚI GIỜ (VN -> UTC)
                        dt_utc = self.parse_datetime_html(current_date_str, result_time)
                        
                        if not dt_utc: continue
                        
                        # Lấy ngày UTC chuẩn để tìm trong DB
                        date_only_utc = dt_utc.strftime('%Y-%m-%d')
                        
                        # 5. UPDATE CHÍNH XÁC (EXACT MATCH)
                        c.execute('''
                            UPDATE economic_events 
                            SET actual = ? 
                            WHERE title = ? 
                            AND currency = ? 
                            AND date(timestamp) = ? 
                            AND (actual IS NULL OR actual = '')
                        ''', (actual, title, currency, date_only_utc))
                        
                        if c.rowcount > 0:
                            logger.info(f"✅ Updated Actual for '{title}' ({currency}): {actual} [Date: {date_only_utc}]")
                            conn.commit()
                            
                    except Exception:
                        continue
                        
        except Exception as e:
            logger.error(f"❌ Error scanning HTML: {e}")

    def parse_datetime_html(self, date_str, time_str):
        """
        Helper: Parse chuỗi ngày giờ từ HTML.
        QUAN TRỌNG: Gán múi giờ 'Asia/Ho_Chi_Minh' rồi đổi sang UTC.
        """
        try:
            if not date_str or not time_str: return None
            
            # Clean: "Tue Dec 16" -> "Dec 16"
            parts = date_str.split()
            if len(parts) > 1:
                clean_date = " ".join(parts[1:])
            else:
                clean_date = date_str
            
            # Tạo chuỗi đầy đủ: "Dec 16 2025 9:45pm"
            full_str = f"{clean_date} {datetime.now().year} {time_str}"
            
            # 1. Parse ra datetime (chưa có múi giờ)
            dt_naive = date_parser.parse(full_str)
            
            # 2. Gán múi giờ Việt Nam (Vì web đang hiển thị giờ VN)
            vn_tz = tz.gettz('Asia/Ho_Chi_Minh')
            dt_vn = dt_naive.replace(tzinfo=vn_tz)
            
            # 3. Đổi sang UTC để khớp với Database
            return dt_vn.astimezone(tz.UTC)
            
        except Exception: 
            return None

    def _format_vn_time(self, utc_timestamp_str):
        try:
            ts = date_parser.parse(utc_timestamp_str)
            if ts.tzinfo is None: ts = ts.replace(tzinfo=tz.UTC)
            vn_tz = tz.gettz('Asia/Ho_Chi_Minh')
            return ts.astimezone(vn_tz).strftime('%H:%M')
        except: return "N/A"

    def process_calendar_alerts(self):
        try:
            # 1. Sync & Update
            self.sync_schedule_to_db()
            
            # Luôn quét HTML để update actual (vì URL mặc định lấy cả tuần)
            self.fetch_realtime_results_html()
            
            now_utc = datetime.now(tz.UTC)
            
            # 2. Pre-Alerts
            pre_alerts = database.get_pending_pre_alerts(60)
            for event in pre_alerts:
                ts = date_parser.parse(event['timestamp'])
                if ts.tzinfo is None: ts = ts.replace(tzinfo=tz.UTC)
                diff = (ts - now_utc).total_seconds() / 60
                
                if diff < -10: 
                    database.update_event_status(event['id'], 'pre_notified')
                    continue

                time_str = self._format_vn_time(event['timestamp'])
                self.send_pre_alert(event, int(diff), time_str)
                database.update_event_status(event['id'], 'pre_notified')
                
            # 3. Post-Alerts
            post_alerts = database.get_pending_post_alerts()
            for event in post_alerts:
                time_str = self._format_vn_time(event['timestamp'])
                self.send_post_alert(event, time_str)
                database.update_event_status(event['id'], 'post_notified')

        except Exception as e:
            logger.error(f"Error process_calendar: {e}")

    def send_pre_alert(self, event, minutes_left, time_str):
        analysis = ai_engine.analyze_pre_economic_data(event)
        
        forecast = event.get('forecast', 'N/A')
        previous = event.get('previous', 'N/A')
        exp = html.escape(analysis.get('explanation', '')) if analysis else ''
        high = html.escape(analysis.get('scenario_high', '')) if analysis else ''
        low = html.escape(analysis.get('scenario_low', '')) if analysis else ''
        
        msg = (
            f"📢 <b>SẮP CÓ TIN MẠNH ({time_str})</b>\n"
            f"⏳ Còn {minutes_left} phút\n\n"
            f"🔥 <b>{event['title']}</b>\n"
            f"⚠️ Tiền tệ: {event['currency']}\n"
            f"📊 <b>Dữ liệu:</b>\n"
            f"   • Dự báo: {forecast}\n"
            f"   • Kỳ trước: {previous}\n\n"
            f"💡 <b>Góc nhìn AI:</b> {exp}\n"
            f"📈 <b>Kịch bản Tăng:</b> {high}\n"
            f"📉 <b>Kịch bản Giảm:</b> {low}\n\n"
            f"#PreNews #{event['currency']}"
        )
        telegram_bot.send_message(msg)
        
    def send_post_alert(self, event, time_str):
        analysis = ai_engine.analyze_economic_data(event)
        
        actual = event.get('actual', 'N/A')
        forecast = event.get('forecast', 'N/A')
        previous = event.get('previous', 'N/A')
        
        if analysis:
            score = analysis.get('sentiment_score', 0)
            icon = "🟢" if score > 0 else "🔴" if score < 0 else "🟡"
            clean_analysis = html.escape(analysis.get('impact_analysis', ''))
            
            msg = (
                f"📢 <b>BẢN TIN KẾT QUẢ ({time_str})</b>\n"
                f"⚡ <b>{event['title']}</b>\n"
                f"--------------------\n"
                f"🔢 <b>Thực tế:  {actual}</b> {icon}\n"
                f"🔹 Dự báo:   {forecast}\n"
                f"🔹 Kỳ trước: {previous}\n"
                f"--------------------\n"
                f"👉 <b>Đánh giá:</b> {score}/10 ({analysis.get('conclusion', '')})\n"
                f"📝 <b>Phân tích:</b> {clean_analysis}\n\n"
                f"#EconomicResult #{event['currency']}"
            )
        else:
            msg = (
                f"📢 <b>BẢN TIN KẾT QUẢ ({time_str})</b>\n"
                f"⚡ <b>{event['title']}</b>\n"
                f"--------------------\n"
                f"🔢 <b>Thực tế:  {actual}</b>\n"
                f"🔹 Dự báo:   {forecast}\n"
                f"🔹 Kỳ trước: {previous}\n"
                f"#EconomicResult"
            )
        telegram_bot.send_message(msg)