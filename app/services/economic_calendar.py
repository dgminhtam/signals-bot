import time
import html
from typing import List, Dict
import logging
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from dateutil import tz
from app.core import config
from app.core import database
from app.services import telegram_bot
from app.services import ai_engine

logger = config.logger

class EconomicCalendarService:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(browser='chrome')
        self.base_url = "https://www.forexfactory.com/calendar"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.5"
        }

    def parse_datetime(self, date_str, time_str):
        try:
            if not date_str or not time_str: return None
            clean_date = " ".join(date_str.split()[1:]) 
            full_str = f"{clean_date} {datetime.now().year} {time_str}"
            dt_naive = date_parser.parse(full_str)
            ny_tz = tz.gettz('America/New_York') or tz.gettz('US/Eastern')
            dt_ny = dt_naive.replace(tzinfo=ny_tz)
            return dt_ny.astimezone(tz.UTC)
        except Exception:
            return None

    def process_calendar_alerts(self):
        try:
            should_fetch = False
            now_utc = datetime.now(tz.UTC)
            
            incomplete = database.get_incomplete_events_today()
            if not incomplete:
                upcoming = database.get_pending_pre_alerts(24*60)
                if not upcoming: should_fetch = True
            else:
                for ev in incomplete:
                    try:
                        ts = date_parser.parse(ev['timestamp'])
                        if ts.tzinfo is None: ts = ts.replace(tzinfo=tz.UTC)
                        diff_min = (ts - now_utc).total_seconds() / 60
                        if diff_min < 30: 
                            should_fetch = True
                            break
                    except: continue
            
            if should_fetch:
                logger.info("🔄 Syncing Economic Calendar...")
                self.sync_events_to_db()

            pre_alerts = database.get_pending_pre_alerts(60)
            for event in pre_alerts:
                ts = date_parser.parse(event['timestamp'])
                if ts.tzinfo is None: ts = ts.replace(tzinfo=tz.UTC)
                diff = (ts - now_utc).total_seconds() / 60
                self.send_pre_alert(event, int(diff))
                database.update_event_status(event['id'], 'pre_notified')
                
            post_alerts = database.get_pending_post_alerts()
            for event in post_alerts:
                self.send_post_alert(event)
                database.update_event_status(event['id'], 'post_notified')

        except Exception as e:
            logger.error(f"Error processing calendar alerts: {e}")

    def sync_events_to_db(self):
        events = self.fetch_events(day="today")
        count = 0
        for ev in events:
            if ev.get('timestamp'):
                database.upsert_economic_event(ev)
                count += 1
        logger.info(f"✅ Synced {count} events to DB.")

    def send_pre_alert(self, event, minutes_left):
        try:
             ts = date_parser.parse(event['timestamp'])
             time_str = ts.astimezone(tz.gettz('Asia/Ho_Chi_Minh')).strftime('%H:%M')
        except:
             time_str = event['time']

        analysis = ai_engine.analyze_pre_economic_data(event)
        
        if analysis:
            exp = html.escape(analysis.get('explanation', ''))
            high = html.escape(analysis.get('scenario_high', ''))
            low = html.escape(analysis.get('scenario_low', ''))
            
            msg = (
                f"📢 <b>BẢN TIN CHUẨN BỊ (Trước {minutes_left}p)</b>\n\n"
                f"🔥 <b>SẮP CÓ TIN MẠNH ({time_str}): {event['title']}</b>\n"
                f"⚠️ Cặp tiền: {event['currency']} Pairs\n"
                f"📊 Dữ liệu: Dự báo {event['forecast']} (Kỳ trước {event['previous']})\n\n"
                f"💡 <b>Phân tích:</b> {exp}\n\n"
                f"↗️ <b>{high}</b>\n"
                f"↘️ <b>{low}</b>\n\n"
                f"#PreNews"
            )
        else:
            msg = (
                f"📢 <b>BẢN TIN CHUẨN BỊ (Trước {minutes_left}p)</b>\n\n"
                f"🔥 <b>SẮP CÓ TIN MẠNH ({time_str}): {event['title']}</b>\n"
                f"⚠️ Cặp tiền: {event['currency']} Pairs\n"
                f"📊 Dữ liệu: Dự báo {event['forecast']} (Kỳ trước {event['previous']})\n\n"
                f"#PreNews"
            )
        telegram_bot.send_message(msg)
        
    def send_post_alert(self, event):
        analysis = ai_engine.analyze_economic_data(event)
        
        if analysis:
            icon = "🟢" if analysis['conclusion'] == "BULLISH" else "🔴" if analysis['conclusion'] == "BEARISH" else "🟡"
            score_icon = "📈" if analysis['sentiment_score'] > 0 else "📉" if analysis['sentiment_score'] < 0 else "➖"
            
            clean_analysis = html.escape(analysis['impact_analysis'])
            
            msg = (
                f"📢 <b>BẢN TIN KẾT QUẢ</b>\n\n"
                f"⚡ <b>KẾT QUẢ TIN: {event['title']}</b>\n"
                f"🔢 Actual: <b>{event['actual']}</b> (Dự báo {event['forecast']}) {score_icon}\n"
                f"👉 <b>Đánh giá:</b> {analysis['sentiment_score']}/10 ({analysis['conclusion']})\n"
                f"📉 <b>Phân tích:</b> {clean_analysis}\n\n"
                f"#EconomicResult"
            )
        else:
            msg = (
                f"📢 <b>BẢN TIN KẾT QUẢ</b>\n\n"
                f"⚡ <b>KẾT QUẢ TIN: {event['title']}</b>\n"
                f"🔢 Actual: <b>{event['actual']}</b> (Dự báo {event['forecast']})\n"
                f"#EconomicResult"
            )
        telegram_bot.send_message(msg)

    def fetch_events(self, day: str = "today") -> List[Dict]:
        url = f"{self.base_url}?day={day}"
        logger.info(f"📅 Fetching Calendar: {url}")
        
        try:
            for attempt in range(3):
                try:
                    response = self.scraper.get(url, headers=self.headers, timeout=20)
                    if response.status_code == 200: break
                except Exception as e:
                    time.sleep(2)
            else:
                return []

            soup = BeautifulSoup(response.content, "html.parser")
            table = soup.find("table", class_="calendar__table")
            if not table: return []
            
            results = []
            rows = table.find_all("tr", class_="calendar__row")
            current_date_str = ""
            
            for row in rows:
                if "calendar__row--new-day" in row.get("class", []):
                    d = row.find("span", class_="date")
                    if d: current_date_str = d.text.strip()
                
                event_id = row.get("data-event-id")
                if not event_id: continue

                is_red = False
                impact_td = row.find("td", class_="calendar__impact")
                if impact_td:
                    sp = impact_td.find("span")
                    if sp and "icon--ff-impact-red" in str(sp.get("class",[])):
                        is_red = True
                if not is_red: continue

                currency = row.find("td", class_="calendar__currency").text.strip()
                event_title = row.find("span", class_="calendar__event-title").text.strip()
                result_time = row.find("td", class_="calendar__time").text.strip()
                actual = row.find("td", class_="calendar__actual").text.strip()
                forecast = row.find("td", class_="calendar__forecast").text.strip()
                previous = row.find("td", class_="calendar__previous").text.strip()
                
                dt_utc = self.parse_datetime(current_date_str, result_time)
                timestamp_iso = dt_utc.strftime('%Y-%m-%d %H:%M:%S') if dt_utc else None

                results.append({
                    "id": event_id,
                    "event": event_title, 
                    "title": event_title,
                    "currency": currency,
                    "impact": "High",
                    "time": result_time,
                    "date": current_date_str,
                    "timestamp": timestamp_iso,
                    "forecast": forecast,
                    "previous": previous,
                    "actual": actual
                }) 
            
            return results
        except Exception as e:
            logger.error(f"Scrape Error: {e}")
            return []
