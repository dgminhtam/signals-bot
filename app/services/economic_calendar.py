import time
from typing import List, Dict
import logging
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from app.core import config
from app.core import database
from app.services import telegram_bot

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
            # date_str: "Thu Dec 12" -> Need Year.
            clean_date = " ".join(date_str.split()[1:]) # "Dec 12"
            full_str = f"{clean_date} {datetime.now().year} {time_str}"
            return date_parser.parse(full_str)
        except Exception:
            return None

    def process_calendar_alerts(self):
        """
        Main logic: Sync DB if needed -> Check Alert
        """
        try:
            should_fetch = False
            now = datetime.now()
            
            # 1. Check logic Fetch
            # Lấy list sự kiện hôm nay chưa có kết quả (Actual = Null)
            incomplete = database.get_incomplete_events_today()
            
            if not incomplete:
                # Check if we have ANY future events in DB? If empty, means we haven't synced today.
                # Heuristic: always sync if empty?
                # Or query pending Pre-alerts for next 24h. If empty, Fetch.
                upcoming = database.get_pending_pre_alerts(24*60)
                if not upcoming:
                    should_fetch = True
            else:
                # Have incomplete events today. Check if update needed.
                for ev in incomplete:
                    try:
                        ts = date_parser.parse(ev['timestamp'])
                        diff_min = (ts - now).total_seconds() / 60
                        # Fetch Condition:
                        # 1. Imminent: < 30 mins
                        # 2. Passed: diff_min < 0 (News passed due but no Actual)
                        # Avoid fetching if diff is too large (future > 30 mins)
                        if diff_min < 30: 
                            should_fetch = True
                            break
                    except: continue
            
            if should_fetch:
                logger.info("🔄 Syncing Economic Calendar from ForexFactory...")
                self.sync_events_to_db()

            # 2. Process Alerts from DB
            # Pre-Alerts (Status = pending, Window 60m)
            pre_alerts = database.get_pending_pre_alerts(60)
            for event in pre_alerts:
                # Verify diff positive? No, 0 to 60.
                diff = (date_parser.parse(event['timestamp']) - now).total_seconds() / 60
                self.send_pre_alert(event, int(diff))
                database.update_event_status(event['id'], 'pre_notified')
                
            # Post-Alerts (Has actual, Status != post_notified)
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
        msg = (
            f"⚠️ <b>SẮP CÓ TIN QUAN TRỌNG ({minutes_left}p)</b>\n\n"
            f"🇺🇸 <b>{event['currency']} - {event['title']}</b>\n"
            f"Expected: {event['forecast']}\n"
            f"Previous: {event['previous']}\n\n"
            f"#NewsAlert"
        )
        telegram_bot.send_message(msg)
        
    def send_post_alert(self, event):
        msg = (
            f"🚨 <b>TIN ĐÃ RA: {event['currency']}</b>\n\n"
            f"Event: <b>{event['title']}</b>\n"
            f"Actual: <b>{event['actual']}</b>\n"
            f"Forecast: {event['forecast']}\n"
            f"Previous: {event['previous']}\n\n"
            f"#EconomicResult"
        )
        telegram_bot.send_message(msg)

    def fetch_events(self, day: str = "today") -> List[Dict]:
        url = f"{self.base_url}?day={day}"
        logger.info(f"📅 Fetching Calendar: {url}")
        
        try:
            # Retry logic
            for attempt in range(3):
                try:
                    response = self.scraper.get(url, headers=self.headers, timeout=20)
                    if response.status_code == 200: break
                except Exception as e:
                    logger.warning(f"Connect FF Error {attempt}: {e}")
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

                # Extract
                currency = row.find("td", class_="calendar__currency").text.strip()
                event_title = row.find("span", class_="calendar__event-title").text.strip()
                result_time = row.find("td", class_="calendar__time").text.strip()
                actual = row.find("td", class_="calendar__actual").text.strip()
                forecast = row.find("td", class_="calendar__forecast").text.strip()
                previous = row.find("td", class_="calendar__previous").text.strip()
                
                dt = self.parse_datetime(current_date_str, result_time)
                timestamp_iso = dt.isoformat() if dt else None

                results.append({
                    "id": event_id,
                    "event": event_title, 
                    # DB uses 'title', Upsert uses event['event'].
                    # But wait, Upsert uses event['event'] in my DB code?
                    # Let's check DB code: upsert_economic_event uses event['event']
                    # So key "event" is correct locally.
                    # I'll add "title" too just in case.
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

if __name__ == "__main__":
    svc = EconomicCalendarService()
    svc.process_calendar_alerts()
