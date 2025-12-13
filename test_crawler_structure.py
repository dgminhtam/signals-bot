
import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def check_structure(name, url):
    print(f"\nChecking {name} ({url})...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.content, "html.parser")
        
        links = soup.find_all('a', href=True)
        count = 0
        for a in links:
            title = a.get_text().strip()
            href = a['href']
            
            if len(title) < 20: continue
            if "javascript:" in href: continue
            
            # Simple keyword check
            if "gold" in title.lower() or "price" in title.lower() or "market" in title.lower() or "fed" in title.lower():
                print(f"[{count+1}] {title[:60]}...")
                print(f"    Link: {href}")
                count += 1
                if count >= 5: break
                
        if count == 0:
            print("No suitable links found (Blocking or Layout change?)")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_structure("CNN Money", "https://edition.cnn.com/business/markets")
    check_structure("CNBC World", "https://www.cnbc.com/precious-metals/")
