import sqlite3
import os
import sys
from datetime import datetime, timedelta
from curl_cffi import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from dateutil import tz

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

DB_PATH = "data/xauusd_news.db"
URL = "https://www.forexfactory.com/calendar"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.5"
}

def get_db_connection():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"❌ DB Connection Failed: {e}")
        return None

def fetch_db_events():
    conn = get_db_connection()
    if not conn: return []
    
    print(f"\n--- 1. FETCHING EVENTS FROM DB ({DB_PATH}) ---")
    c = conn.cursor()
    
    # Get High/Medium events for Yesterday, Today, Tomorrow
    # Note: SQLite 'date(timestamp)' assumes UTC or stored ISO string
    c.execute('''
        SELECT title, currency, timestamp, status, actual, impact 
        FROM economic_events 
        WHERE impact IN ('High', 'Medium')
        ORDER BY timestamp DESC
        LIMIT 20
    ''')
    
    rows = c.fetchall()
    events = []
    
    for row in rows:
        ts = date_parser.parse(row['timestamp'])
        title = row['title']
        currency = row['currency']
        date_only = ts.strftime('%Y-%m-%d')
        
        events.append({
            "title": title,
            "currency": currency,
            "date": date_only,
            "status": row['status'],
            "actual": row['actual'],
            "original_row": dict(row)
        })
        print(f"[DB] Found: {title} ({currency}) | Date: {date_only} | Status: {row['status']} | Actual: {row['actual']}")
        
    conn.close()
    return events

def parse_datetime_html(date_str, time_str):
    try:
        if not date_str or not time_str: return None
        clean_date = " ".join(date_str.split()[1:]) if len(date_str.split()) > 1 else date_str
        full_str = f"{clean_date} {datetime.now().year} {time_str}"
        dt_naive = date_parser.parse(full_str)
        ny_tz = tz.gettz('America/New_York')
        dt_ny = dt_naive.replace(tzinfo=ny_tz)
        return dt_ny.astimezone(tz.UTC)
    except: return None

def fetch_html_events():
    print(f"\n--- 2. SCANNING HTML ({URL}) ---")
    try:
        response = requests.get(URL, headers=HEADERS, impersonate="chrome120", timeout=30)
        if response.status_code != 200:
            print(f"❌ Request failed: {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.content, "html.parser")
        table = soup.find("table", class_="calendar__table")
        if not table:
            print("❌ Calendar table not found")
            return []
            
        rows = table.find_all("tr", class_="calendar__row")
        current_date_str = ""
        last_time_str = ""
        html_events = []
        
        for row in rows:
            if "calendar__row--new-day" in row.get("class", []):
                d_tag = row.find("span", class_="date")
                if d_tag: 
                    current_date_str = " ".join(d_tag.text.strip().split()[:3])
                    last_time_str = ""
            
            title_tag = row.find("span", class_="calendar__event-title")
            currency_tag = row.find("td", class_="calendar__currency")
            actual_tag = row.find("td", class_="calendar__actual")
            time_tag = row.find("td", class_="calendar__time")
            
            if not title_tag or not currency_tag or not actual_tag: continue
            
            title = title_tag.text.strip()
            currency = currency_tag.text.strip()
            actual = actual_tag.text.strip()
            
            # Skip empty actual
            if not actual: continue
            
            time_str = time_tag.text.strip() if time_tag else ""
            
            if time_str:
                last_time_str = time_str
            elif last_time_str:
                time_str = last_time_str
                
            dt_utc = parse_datetime_html(current_date_str, time_str)
            
            if not dt_utc:
                print(f"⚠️ Failed to parse date: {current_date_str} {time_str}")
                continue
                
            date_only = dt_utc.strftime('%Y-%m-%d')
            
            # Filter matches only matching DB criteria for debugging (High/Med)
            # Or just print all found with actual
            html_events.append({
                "title": title,
                "currency": currency,
                "date": date_only,
                "actual": actual
            })
            print(f"[HTML] Found: {title} ({currency}) | Date: {date_only} | Actual: {actual}")
            
        return html_events
        
    except Exception as e:
        print(f"❌ Error scraping HTML: {e}")
        return []

def compare_results(db_events, html_events):
    print(f"\n--- 3. DETAILED COMPARISON DIAGNOSIS ---")
    
    matching_found = 0
    
    for html_e in html_events:
        print(f"\n🔎 Checking HTML Event: [{html_e['title']}] ({html_e['currency']}) - {html_e['date']}")
        
        # Try to find match in DB
        match = None
        mismatch_reasons = []
        
        for db_e in db_events:
            # Check 1: Currency (Usually reliable)
            if db_e['currency'] != html_e['currency']:
                continue
                
            # Check 2: Date
            if db_e['date'] != html_e['date']:
                # mismatch_reasons.append(f"Currency match but Date mismatch: DB={db_e['date']} vs HTML={html_e['date']}")
                continue
            
            # Check 3: Title (Most likely culprit)
            # Exact string match?
            if db_e['title'] == html_e['title']:
                match = db_e
                break
            else:
                mismatch_reasons.append(f"Potential Match Failed on Title: DB='{db_e['title']}' != HTML='{html_e['title']}'")
        
        if match:
            print(f"   ✅ MATCH FOUND in DB! Status: {match['status']}")
            if match['actual'] == html_e['actual']:
                print(f"   👌 Data synced correctly: {match['actual']}")
            else:
                print(f"   ⚠️ Data OUT OF SYNC: DB has '{match['actual']}', HTML has '{html_e['actual']}'")
            matching_found += 1
        else:
            print(f"   ❌ NO EXACT MATCH FOUND IN DB.")
            if mismatch_reasons:
                for reason in mismatch_reasons:
                    print(f"      -> {reason}")
            else:
                print("      -> No DB record found with matching Currency & Date.")

    print(f"\n\n=== SUMMARY ===")
    print(f"Total HTML Events with Actual: {len(html_events)}")
    print(f"Total Matches in DB: {matching_found}")
    print(f"Unmatched: {len(html_events) - matching_found}")

if __name__ == "__main__":
    db_events = fetch_db_events()
    html_events = fetch_html_events()
    compare_results(db_events, html_events)
