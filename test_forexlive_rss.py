import requests
import feedparser

urls_to_test = [
    ("investinglive.com/feed/news (current config)", "https://investinglive.com/feed/news"),
    ("forexlive.com/feed (correct URL)", "https://www.forexlive.com/feed/"),
    ("forexlive.com/feed/news (old config)", "https://www.forexlive.com/feed/news"),
]



HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

with open("results_forexlive_full_headers.txt", "w", encoding="utf-8") as f:
    for name, url in urls_to_test:
        f.write("=" * 70 + "\n")
        f.write(f"Testing: {name}\n")
        f.write(f"URL: {url}\n")
        f.write("=" * 70 + "\n")
        try:
            response = requests.get(url, timeout=10, headers=HEADERS)
            f.write(f"Status Code: {response.status_code}\n")

            f.write(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}\n")
            f.write(f"Content Length: {len(response.content)} bytes\n")
            
            if response.status_code == 200:
                # Try to parse as RSS
                feed = feedparser.parse(response.content)
                f.write(f"Feed Title: {feed.feed.get('title', 'N/A')}\n")
                f.write(f"Feed Entries: {len(feed.entries)}\n")
                
                if feed.bozo:
                    f.write(f"⚠️ Parsing Warning: {feed.bozo_exception}\n")
                else:
                    f.write("✅ Valid RSS Feed!\n")
                    if feed.entries:
                        f.write(f"\nFirst Entry:\n")
                        f.write(f"  - Title: {feed.entries[0].get('title', 'N/A')}\n")
                        f.write(f"  - Link: {feed.entries[0].get('link', 'N/A')}\n")
                        f.write(f"  - Published: {feed.entries[0].get('published', 'N/A')}\n")
            else:
                f.write(f"❌ Failed with status {response.status_code}\n")
                
        except Exception as e:
            f.write(f"❌ Error: {type(e).__name__}: {e}\n")
        
        f.write("\n")

