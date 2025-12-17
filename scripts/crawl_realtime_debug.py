import json
import os
import sys
from datetime import datetime
from curl_cffi import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# Ensure data directory exists
os.makedirs("data", exist_ok=True)

URLS = [
    "https://www.forexfactory.com/calendar"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.5"
}

OUTPUT_FILE = "data/debug_actuals.json"

def fetch_and_parse():
    all_events = []
    
    print(f"🚀 Starting crawl...")
    print(f"📂 Output will be saved to: {OUTPUT_FILE}")

    current_year = datetime.now().year

    for url in URLS:
        print(f"\n📡 Requesting: {url}")
        try:
            response = requests.get(url, headers=HEADERS, impersonate="chrome120", timeout=30)
            if response.status_code != 200:
                print(f"❌ Failed to fetch {url}: {response.status_code}")
                continue
            
            soup = BeautifulSoup(response.content, "html.parser")
            table = soup.find("table", class_="calendar__table")
            if not table:
                print(f"⚠️ No calendar table found in {url}")
                continue
            
            rows = table.find_all("tr", class_="calendar__row")
            
            current_date_str = None
            parsed_date_str = None
            last_time_str = ""
            
            # Helper to clean date text (remove extra info like 'Oct Data')
            def clean_date_text(text):
                parts = text.strip().split()
                if len(parts) >= 3:
                     # Take only first 3 parts: e.g. "Mon", "Dec", "15"
                     return " ".join(parts[:3])
                return text.strip()

            for row in rows:
                # 1. Check for new day header (Date handling)
                if "calendar__row--new-day" in row.get("class", []):
                    d_tag = row.find("span", class_="date")
                    if d_tag:
                        raw_date = d_tag.text.strip()
                        current_date_str = clean_date_text(raw_date)
                        last_time_str = "" # Reset time for new day
                        
                        # Parse date
                        try:
                            # Append current year to make it parseable as a full date
                            dt = date_parser.parse(f"{current_date_str} {current_year}")
                            parsed_date_str = dt.strftime("%Y-%m-%d")
                        except Exception as e:
                            print(f"⚠️ Date parse error '{current_date_str}': {e}")
                            parsed_date_str = None

                # 2. Extract Fields
                title_tag = row.find("span", class_="calendar__event-title")
                currency_tag = row.find("td", class_="calendar__currency")
                actual_tag = row.find("td", class_="calendar__actual")
                forecast_tag = row.find("td", class_="calendar__forecast")
                time_tag = row.find("td", class_="calendar__time")

                # Skip invalid rows (e.g. ad rows or separators without title)
                if not title_tag:
                    continue
                
                # Handling Time (Contextual filling for grouped events)
                time_val = time_tag.text.strip() if time_tag else ""
                if time_val:
                    last_time_str = time_val
                elif last_time_str:
                    # If time is empty, inherit from previous row in the same block
                    time_val = last_time_str

                event_data = {
                    "raw_date": current_date_str,
                    "parsed_date": parsed_date_str,
                    "time": time_val,
                    "currency": currency_tag.text.strip() if currency_tag else "",
                    "event": title_tag.text.strip(),
                    "actual": actual_tag.text.strip() if actual_tag else "",
                    "forecast": forecast_tag.text.strip() if forecast_tag else ""
                }

                all_events.append(event_data)

                # Print to console if Actual exists (Visual check)
                if event_data['actual']:
                    print(f"✅ [{event_data['parsed_date']} {event_data['time']}] {event_data['currency']} - {event_data['event']}: {event_data['actual']}")

        except Exception as e:
            print(f"❌ Error processing {url}: {e}")

    # Save to JSON
    print(f"\n💾 Saving {len(all_events)} events to JSON...")
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_events, f, indent=2, ensure_ascii=False)
        print("✅ Done.")
    except Exception as e:
        print(f"❌ Failed to write output file: {e}")

if __name__ == "__main__":
    fetch_and_parse()
