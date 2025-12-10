# debug_rss.py
import requests
import feedparser
import config
from database import check_keywords
from dateutil import parser
from datetime import datetime, timezone, timedelta

logger = config.logger

def debug_connection(url, name):
    print(f"\n--- DEBUG CONNECT: {name} ---")
    print(f"URL: {url}")
    try:
        # Thử request thường
        resp = requests.get(url, headers=config.HEADERS, timeout=15)
        print(f"Status Code: {resp.status_code}")
        print(f"Content Length: {len(resp.content)}")
        print(f"Content Preview: {resp.text[:200]}")
        
        if resp.status_code != 200:
            print("❌ Lỗi: Status code không phải 200")
            return
            
        # Thử feedparser
        feed = feedparser.parse(resp.content)
        if not feed.entries:
            print(f"❌ Feedparser không tìm thấy entries. Bozo status: {getattr(feed, 'bozo', 'N/A')}")
            if hasattr(feed, 'bozo_exception'):
                print(f"   Bozo Exception: {feed.bozo_exception}")
        else:
            print(f"✅ Feedparser OK: {len(feed.entries)} entries")
            # Kiếm tra entry đầu tiên
            entry = feed.entries[0]
            print(f"   Sample Entry Title: {entry.get('title')}")
            print(f"   Sample Entry Link: {entry.get('link')}")
            print(f"   Sample Entry PubDate: {entry.get('published', entry.get('updated', 'N/A'))}")
            
            # Test Logic lọc
            check_filter_logic(entry)

    except Exception as e:
        print(f"❌ Exception: {e}")

def check_filter_logic(entry):
    print("\n   --- DEBUG FILTER LOGIC ---")
    title = entry.get("title", "")
    summary = entry.get("summary", "")
    content_check = title + " " + summary
    
    # Check 1: Time
    published = entry.get("published", entry.get("updated", ""))
    is_time_ok = False
    if published:
        try:
            pub_date = parser.parse(published)
            if pub_date.tzinfo is None: pub_date = pub_date.replace(tzinfo=timezone.utc)
            
            now_utc = datetime.now(timezone.utc)
            time_limit = now_utc - timedelta(hours=24)
            
            print(f"   Time Limit: {time_limit}")
            print(f"   Pub Date:   {pub_date}")
            
            if pub_date >= time_limit:
                is_time_ok = True
                print("   ✅ Time Check: PRECENT (Hợp lệ)")
            else:
                print("   ❌ Time Check: OLD (Quá cũ)")
        except Exception as e:
            print(f"   ❌ Time Parse Error: {e}")
    else:
        print("   ❌ Time Missing")

    # Check 2: Keywords
    matched_kws = check_keywords(content_check)
    print(f"   Content to check: {content_check[:100]}...")
    if matched_kws:
        print(f"   ✅ Keyword Check: MATCHED {matched_kws}")
    else:
        print(f"   ❌ Keyword Check: FAILED (Keywords: {config.KEYWORDS_DIRECT + config.KEYWORDS_CORRELATION})")

def main():
    print("=== BẮT ĐẦU DEBUG RSS ===")
    
    # Debug từng nguồn
    for source in config.RSS_SOURCES:
        debug_connection(source["url"], source["name"])

if __name__ == "__main__":
    main()
