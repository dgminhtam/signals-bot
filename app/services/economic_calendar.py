import time
import html
import json
import os
import asyncio
from typing import List, Dict, Optional
import logging
from datetime import datetime, timedelta
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from dateutil import tz
from app.core import config
from app.core import database
from app.services import telegram_bot
from app.services import ai_engine
from app.services.trader import AutoTrader

logger = config.logger

SCHEDULE_JSON_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CACHE_FILE = "data/ff_schedule.json"
CACHE_TTL = 3600  # 60 minutes

class EconomicCalendarService:
    def __init__(self):
        # 1. URL Mặc định (Scan cả tuần)
        self.base_url = "https://www.forexfactory.com/calendar"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.5"
        }
        if not os.path.exists("data"):
            os.makedirs("data")

    async def _fetch_url(self, url: str):
        """
        Helper: Browser Rotation & Retry Mechanism (Async)
        """
        browsers = ["chrome120", "safari15_5", "chrome110", "edge101", "safari_ios_16_5"]
        
        async with AsyncSession(timeout=30) as session:
            for browser in browsers:
                try:
                    response = await session.get(url, headers=self.headers, impersonate=browser)
                    
                    if response.status_code == 200:
                        return response
                    elif response.status_code == 403:
                        logger.warning(f"⚠️ Blocked 403 ({browser}). Retrying in 3s...")
                        await asyncio.sleep(3)
                    else:
                        logger.warning(f"⚠️ Failed {response.status_code} ({browser}). Retrying...")
                        await asyncio.sleep(3)

                except Exception as e:
                    logger.warning(f"❌ Connection Error ({browser}): {e}")
                    await asyncio.sleep(3)
        
        logger.error(f"❌ All browsers failed to fetch URL: {url}")
        return None

    async def fetch_schedule_json(self) -> List[Dict]:
        """
        Lấy lịch sự kiện từ JSON API (Async). 
        """
        try:
            # Check Cache (IO Sync is acceptable for reading small JSON file)
            loop = asyncio.get_running_loop()
            if os.path.exists(CACHE_FILE):
                mod_time = os.path.getmtime(CACHE_FILE)
                if time.time() - mod_time < CACHE_TTL:
                    with open(CACHE_FILE, 'r') as f:
                        return await loop.run_in_executor(None, json.load, f)
            
            logger.info(f"🌐 Fetching Schedule JSON: {SCHEDULE_JSON_URL}")
            # USE ROTATION
            response = await self._fetch_url(SCHEDULE_JSON_URL)
            
            if response and response.status_code == 200:
                data = response.json()
                # Write Cache Async
                await loop.run_in_executor(None, self._write_cache, data)
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching schedule JSON: {e}")
            return []

    def _write_cache(self, data):
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f)

    async def sync_schedule_to_db(self):
        """
        Đồng bộ từ JSON vào DB (Async).
        """
        events = await self.fetch_schedule_json()
        if not events: return

        count = 0
        async with database.get_db_connection() as conn:
            for item in events:
                try:
                    title = item.get('title', 'Unknown')
                    currency = item.get('country', 'USD')
                    impact = item.get('impact', 'Low')
                    
                    # Filter High Impact Only (SIẾT CHẶT)
                    if impact != 'High': 
                        continue

                    # JSON date -> UTC
                    date_str = item.get('date')
                    dt = date_parser.parse(date_str)
                    dt_utc = dt.astimezone(tz.UTC)
                    timestamp_iso = dt_utc.strftime('%Y-%m-%d %H:%M:%S')
                    date_only = dt_utc.strftime('%Y-%m-%d')
                    
                    # Generate ID
                    safe_title = title.replace(" ", "_").replace("/", "").replace(":", "")
                    id_str = f"{timestamp_iso}_{currency}_{safe_title}"
                    
                    # 1. Preserve Status
                    existing_status = 'pending'
                    async with conn.execute('''
                        SELECT status FROM economic_events
                        WHERE title = ? 
                        AND currency = ? 
                        AND date(timestamp) BETWEEN date(?, '-1 day') AND date(?, '+1 day')
                    ''', (title, currency, date_only, date_only)) as cursor:
                         rows = await cursor.fetchall()
                         for r in rows:
                            if r['status'] in ['pre_notified', 'post_notified']:
                                existing_status = r['status']
                                break

                    # 2. Cleanup Duplicates
                    await conn.execute('''
                        DELETE FROM economic_events 
                        WHERE title = ? 
                        AND currency = ? 
                        AND date(timestamp) BETWEEN date(?, '-1 day') AND date(?, '+1 day')
                    ''', (title, currency, date_only, date_only))

                    # 3. Insert New
                    await conn.execute('''
                        INSERT INTO economic_events (id, title, currency, impact, timestamp, forecast, previous, actual, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        id_str, title, currency, impact, timestamp_iso, 
                        item.get('forecast', ''), 
                        item.get('previous', ''), 
                        "", # Actual empty
                        existing_status
                    ))
                    count += 1
                except Exception as e:
                    logger.error(f"❌ Lỗi khi import '{item.get('title', 'Unknown')}': {str(e)}")
                    continue
            
            await conn.commit()
        logger.info(f"✅ Synced {count} High events to DB.")

    async def fetch_realtime_results_html(self):
        """
        Quét HTML để lấy `Actual` value (Async).
        """
        url = self.base_url  # URL default (Weekly view)
        logger.info(f"⚡ Scanning Real-time HTML (Weekly View): {url}")
        
        try:
            # USE ROTATION
            response = await self._fetch_url(url)
            
            if not response or response.status_code != 200: return

            # Parsing HTML is CPU bound
            soup = BeautifulSoup(response.content, "html.parser")
            table = soup.find("table", class_="calendar__table")
            if not table: return
            
            rows = table.find_all("tr", class_="calendar__row")
            current_date_str = ""
            last_time_str = ""
            
            async with database.get_db_connection() as conn:
                for row in rows:
                    try:
                        # 1. Extract Date Header
                        if "calendar__row--new-day" in row.get("class", []):
                            d_tag = row.find("span", class_="date")
                            if d_tag:
                                raw_date = d_tag.text.strip()
                                current_date_str = " ".join(raw_date.split()[:3])
                                last_time_str = ""
                        
                        if "data-event-id" not in row.attrs: continue

                        # 2. Extract Fields
                        title_tag = row.find("span", class_="calendar__event-title")
                        currency_tag = row.find("td", class_="calendar__currency")
                        actual_tag = row.find("td", class_="calendar__actual")
                        
                        if not title_tag or not currency_tag or not actual_tag: continue

                        title = title_tag.text.strip()
                        currency = currency_tag.text.strip()
                        actual = actual_tag.text.strip()
                        
                        if not actual: continue 

                        # 3. Handle Time
                        time_tag = row.find("td", class_="calendar__time")
                        result_time = time_tag.text.strip() if time_tag else ""
                        
                        if result_time:
                            last_time_str = result_time
                        elif last_time_str:
                            result_time = last_time_str 
                        
                        # 4. CRITICAL: Parse & Convert Timezone (VN -> UTC)
                        dt_utc = self.parse_datetime_html(current_date_str, result_time)
                        if not dt_utc: continue
                        
                        date_only_utc = dt_utc.strftime('%Y-%m-%d')
                        
                        # 5. EXACT MATCH UPDATE
                        await conn.execute('''
                            UPDATE economic_events 
                            SET actual = ? 
                            WHERE title = ? 
                            AND currency = ? 
                            AND date(timestamp) = ? 
                            AND (actual IS NULL OR actual = '')
                        ''', (actual, title, currency, date_only_utc))
                        conn.total_changes
                        # Check rowcount if possible, simplified here
                        
                    except Exception: continue
                await conn.commit()
                        
        except Exception as e:
            logger.error(f"❌ Error scanning HTML: {e}")

    def parse_datetime_html(self, date_str, time_str):
        """
        Parse HTML Date/Time string (Sync Helper - Fast).
        """
        try:
            if not date_str or not time_str: return None
            
            parts = date_str.split()
            if len(parts) > 1:
                clean_date = " ".join(parts[1:])
            else:
                clean_date = date_str
            
            current_year = datetime.now().year
            full_str = f"{clean_date} {current_year} {time_str}"
            
            # 1. Parse Naive
            dt_naive = date_parser.parse(full_str)
            
            # 2. FORCE Local Timezone (VN)
            vn_tz = tz.gettz('Asia/Ho_Chi_Minh')
            dt_vn = dt_naive.replace(tzinfo=vn_tz)
            
            # 3. Convert to UTC
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

    async def process_calendar_alerts(self):
        """
        Main Flow (Async)
        """
        try:
            # Sync Schedule
            await self.sync_schedule_to_db()
            
            # Update Actuals
            await self.fetch_realtime_results_html()
            
            now_utc = datetime.now(tz.UTC)
            
            # Pre Alerts
            pre_alerts = await database.get_pending_pre_alerts(60)
            for event in pre_alerts:
                ts = date_parser.parse(event['timestamp']) # UTC
                if ts.tzinfo is None: ts = ts.replace(tzinfo=tz.UTC)
                diff = (ts - now_utc).total_seconds() / 60
                
                if diff < -10:
                    await database.update_event_status(event['id'], 'pre_notified')
                    continue
                
                time_str = self._format_vn_time(event['timestamp'])
                await self.send_pre_alert(event, int(diff), time_str)
                await database.update_event_status(event['id'], 'pre_notified')
                
            # Post Alerts
            post_alerts = await database.get_pending_post_alerts()
            for event in post_alerts:
                time_str = self._format_vn_time(event['timestamp'])
                await self.send_post_alert(event, time_str)
                await database.update_event_status(event['id'], 'post_notified')

            # --- TRAP TRADING (STRADDLE) ---
            # Check for High Impact USD news in 2 minutes
            trap_events = await database.get_events_for_trap(min_minutes=1.5, max_minutes=2.5)
            if trap_events:
                logger.info(f"⏰ Pre-News Alert! {len(trap_events)} High Impact USD event(s) in ~2 mins.")
                for ev in trap_events:
                    logger.info(f"   -> Setup Trap for: {ev['title']}")
                
                # Activate AutoTrader Trap
                try:
                    trader = AutoTrader("XAUUSD") # Default XAUUSD for News Trap
                    tickets = await trader.place_straddle_orders(distance_pips=20, sl_pips=10, tp_pips=30)
                    
                    if tickets:
                        logger.info(f"   ✅ Trap Placed: {tickets}. Scheduling cleanup in 15m.")
                        # Schedule Cleanup Task (Fire & Forget)
                        asyncio.create_task(self._schedule_cleanup(trader, tickets, delay=15*60))
                except Exception as e:
                    logger.error(f"   ❌ Trap Setup Failed: {e}")
                    
        except Exception as e:
            logger.error(f"Error in process_calendar_alerts: {e}")

    async def _schedule_cleanup(self, trader: AutoTrader, tickets: List[str], delay: float):
        """Helper to cleanup pending orders after delay"""
        await asyncio.sleep(delay)
        await trader.cleanup_pending_orders(tickets)

    async def send_pre_alert(self, event, minutes_left, time_str):
        # AI Engine Async Call
        analysis = await ai_engine.analyze_pre_economic_data(event)
        
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
            f"💡 <b>Phân tích:</b> {exp}\n"
            f"📈 <b>Kịch bản tăng:</b> {high}\n"
            f"📉 <b>Kịch bản giảm:</b> {low}\n\n"
            f"#PreNews #{event['currency']}"
        )
        await telegram_bot.send_message_async(msg)
        
    async def send_post_alert(self, event, time_str):
        analysis = await ai_engine.analyze_economic_data(event)
        
        actual = event.get('actual', 'N/A')
        forecast = event.get('forecast', 'N/A')
        previous = event.get('previous', 'N/A')
        
        if analysis:
            sentiment_score = analysis.get('sentiment_score', 0)
            icon = "🟢" if sentiment_score > 0 else "🔴" if sentiment_score < 0 else "🟡"
            clean_analysis = html.escape(analysis.get('impact_analysis', ''))
            
            msg = (
                f"📢 <b>BẢN TIN KẾT QUẢ ({time_str})</b>\n"
                f"⚡ <b>{event['title']}</b>\n"
                f"--------------------\n"
                f"🔢 <b>Thực tế:  {actual}</b> {icon}\n"
                f"🔹 Dự báo:   {forecast}\n"
                f"🔹 Kỳ trước: {previous}\n"
                f"--------------------\n"
                f"👉 <b>Đánh giá:</b> {sentiment_score}/10 ({analysis.get('conclusion', '')})\n"
                f"📝 <b>Phân tích:</b> {clean_analysis}\n\n"
                f"#EconomicResult #{event['currency']}"
            )
            
            # --- TRIGGER AUTO TRADER (Async) ---
            try:
                if abs(sentiment_score) >= 5:
                    logger.info(f"🤖 Activating AutoTrader on Economic Result (Score: {sentiment_score})...")
                    trader = AutoTrader()
                    
                    score_norm = abs(sentiment_score)
                    trend = "BULLISH" if sentiment_score > 0 else "BEARISH"
                    
                    news_data = {
                        'title': event.get('title', 'Economic Data'),
                        'score': score_norm,
                        'trend': trend
                    }
                    await trader.process_news_signal(news_data)
            except Exception as e:
                logger.error(f"❌ Trader Trigger Error: {e}")
                
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
        await telegram_bot.send_message_async(msg)