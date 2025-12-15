import requests
import feedparser

urls_to_test = [
    ("investing.com (current config)", "https://www.investing.com/rss/news_25.rss"),
    ("investing.com (commodities)", "https://www.investing.com/rss/news_11.rss"),
    ("investing.com (forex)", "https://www.investing.com/rss/news_1.rss"),
    ("investing.com (general)", "https://www.investing.com/rss/news.rss"),
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}


with open("results_investing.txt", "w", encoding="utf-8") as f:
    for name, url in urls_to_test:
        f.write("=" * 70 + "\n")
        f.write(f"Testing: {name}\n")
        f.write(f"URL: {url}\n")
        f.write("=" * 70 + "\n")
        try:
            response = requests.get(url, timeout=10, headers=headers)
            f.write(f"Status Code: {response.status_code}\n")
            
            if response.status_code == 200:
                # Try to parse as RSS
                feed = feedparser.parse(response.content)
                f.write(f"Feed Title: {feed.feed.get('title', 'N/A')}\n")
                f.write(f"Feed Entries: {len(feed.entries)}\n")
                
                if feed.bozo:
                    f.write(f"⚠️ Parsing Warning: {feed.bozo_exception}\n")
                else:
                    f.write("✅ Valid RSS Feed!\n")
            else:
                f.write(f"❌ Failed with status {response.status_code}\n")
                
        except Exception as e:
            f.write(f"❌ Error: {type(e).__name__}: {e}\n")
        
        f.write("\n")

