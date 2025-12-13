import time
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
        """
        Parse FF time (likely New York Time) string to UTC datetime.
        """
        try:
            if not date_str or not time_str: return None
            # Input: "Dec 13", "8:30pm"
            # FF shows "Dec 13" based on NY Time? Assuming yes.
            
            clean_date = " ".join(date_str.split()[1:]) # "Dec 12"
            full_str = f"{clean_date} {datetime.now().year} {time_str}"
            
            # Parse naive (implies local time of the string context, which is NY)
            dt_naive = date_parser.parse(full_str)
            
            # Assign NY Timezone
            ny_tz = tz.gettz('America/New_York')
            if not ny_tz: ny_tz = tz.gettz('US/Eastern')
            
            dt_ny = dt_naive.replace(tzinfo=ny_tz)
            
            # Convert to UTC
            dt_utc = dt_ny.astimezone(tz.UTC)
            
            return dt_utc
        except Exception as e:
            # logger.warning(f"Parse error: {e}")
            return None

    def process_calendar_alerts(self):
        try:
            should_fetch = False
            # Current time in UTC for comparison
            now_utc = datetime.now(tz.UTC)
            
            incomplete = database.get_incomplete_events_today()
            
            if not incomplete:
                upcoming = database.get_pending_pre_alerts(24*60)
                if not upcoming:
                    should_fetch = True
            else:
                for ev in incomplete:
                    try:
                        # ev['timestamp'] should be ISO UTC
                        ts = date_parser.parse(ev['timestamp'])
                        # Ensure ts is aware (if DB saved naive strings previously, parser might make naive)
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=tz.UTC)
                            
                        diff_min = (ts - now_utc).total_seconds() / 60
                        
                        # Fetch if close (< 30 mins) OR Past (diff < 0)
                        if diff_min < 30: 
                            should_fetch = True
                            break
                    except: continue
            
            if should_fetch:
                logger.info("🔄 Syncing Economic Calendar (Checking UTC logic)...")
                self.sync_events_to_db()

            # Pre-Alerts
            pre_alerts = database.get_pending_pre_alerts(60)
            for event in pre_alerts:
                ts = date_parser.parse(event['timestamp'])
                if ts.tzinfo is None: ts = ts.replace(tzinfo=tz.UTC)
                
                diff = (ts - now_utc).total_seconds() / 60
                # Alert if within 0..60 mins
                self.send_pre_alert(event, int(diff))
                database.update_event_status(event['id'], 'pre_notified')
                
            # Post-Alerts
            post_alerts = database.get_pending_post_alerts()
            for event in post_alerts:
                self.send_post_alert(event)
                database.update_event_status(event['id'], 'post_notified')

        except Exception as e:
            logger.error(f"Error processing calendar alerts: {e}")

    def sync_events_to_db(self):
        events = self.fetch_events(day="today")
        # Ensure we also scrape yesterday/tomorrow if boundary issues?
        # For now 'today' logic.
        count = 0
        for ev in events:
            if ev.get('timestamp'):
                database.upsert_economic_event(ev)
                count += 1
        logger.info(f"✅ Synced {count} events to DB.")

    def send_pre_alert(self, event, minutes_left):
        # Format time for display (Local or NY?)
        # Let's show UTC or convert to VN (UTC+7)?
        # For now show RAW from DB might be UTC ISO.
        # Ideally nice 24h format.
        
        try:
             ts = date_parser.parse(event['timestamp'])
             time_str = ts.astimezone(tz.gettz('Asia/Ho_Chi_Minh')).strftime('%H:%M')
        except:
             time_str = event['time'] # Fallback
             
        msg = (
            f"⚠️ <b>SẮP CÓ TIN: {event['title']} ({minutes_left}p)</b>\n\n"
            f"🕒 Giờ tin: <b>{time_str}</b> (VN)\n"
            f"🇺🇸 <b>{event['currency']}</b>\n"
            f"Expected: {event['forecast']}\n"
            f"Previous: {event['previous']}\n"
            f"#NewsPreAlert"
        )
        telegram_bot.send_message(msg)
        
    def send_post_alert(self, event):
        # AI Analysis
        analysis = ai_engine.analyze_economic_data(event)
        
        if analysis:
            icon = "🟢" if analysis['conclusion'] == "BULLISH" else "🔴" if analysis['conclusion'] == "BEARISH" else "🟡"
            score_icon = "📈" if analysis['sentiment_score'] > 0 else "📉" if analysis['sentiment_score'] < 0 else "➖"
            
            msg = (
                f"{analysis['headline']}\n\n"
                f"🇺🇸 <b>Tin: {event['title']}</b>\n"
                f"Actual: <b>{event['actual']}</b> (Fcst: {event['forecast']})\n\n"
                f"🧠 <b>AI Phân Tích (Kiều):</b>\n"
                f"{analysis['impact_analysis']}\n\n"
                f"{score_icon} <b>Score:</b> {analysis['sentiment_score']}/10\n"
                f"{icon} <b>Tín hiệu Vàng:</b> {analysis['conclusion']}\n\n"
                f"#EconomicAI"
            )
        else:
            # Fallback
            msg = (
                f"🚨 <b>TIN ĐÃ RA: {event['currency']}</b>\n\n"
                f"Event: <b>{event['title']}</b>\n"
                f"Actual: <b>{event['actual']}</b>\n"
                f"Forecast: {event['forecast']}\n"
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

                # Impact
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
                
                # Parse to UTC
                dt_utc = self.parse_datetime(current_date_str, result_time)
                timestamp_iso = dt_utc.isoformat() if dt_utc else None

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
