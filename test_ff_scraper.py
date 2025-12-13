
import requests
from bs4 import BeautifulSoup
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.google.com/"
}

def test_ff():
    url = "https://www.forexfactory.com/calendar?day=today"
    print(f"Fetching {url}...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        print(f"Status Code: {resp.status_code}")
        
        soup = BeautifulSoup(resp.content, "html.parser")
        table = soup.find("table", class_="calendar__table")
        
        if not table:
            print("❌ No calendar table found. Possible Anti-Scraping blocking.")
            # Print title to see if it's Cloudflare challenge
            print("Page Title:", soup.title.text.strip() if soup.title else "No Title")
            return

        print("✅ Found calendar table. Parsing rows...")
        rows = table.find_all("tr", class_="calendar__row")
        print(f"Found {len(rows)} rows.")
        
        for row in rows[:10]: # Check first 10
            # Impact
            impact_span = row.find("span", class_="calendar__impact-icon")
            impact_class = impact_span["class"] if impact_span else []
            impact = "High" if "calendar__impact-icon--high" in str(impact_class) else "Low/Med"
            
            # Currency
            currency = row.find("td", class_="calendar__currency")
            currency_text = currency.text.strip() if currency else ""
            
            # Event
            event = row.find("span", class_="calendar__event-title")
            event_text = event.text.strip() if event else ""
            
            # Time
            time_td = row.find("td", class_="calendar__time")
            time_text = time_td.text.strip() if time_td else ""
            
            if impact == "High":
                print(f"🔴 [{time_text}] {currency_text} - {event_text}")
            elif event_text:
                print(f"⚪ [{time_text}] {currency_text} - {event_text} ({impact})")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_ff()
