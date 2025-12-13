
import cloudscraper

def dump_html():
    scraper = cloudscraper.create_scraper(browser='chrome')
    url = "https://www.forexfactory.com/calendar?day=dec12.2024"
    print(f"Fetching {url}...")
    try:
        resp = scraper.get(url, headers={"Accept-Language": "en-US,en;q=0.5"})
        print(f"Status: {resp.status_code}")
        with open("ff_debug.html", "wb") as f:
            f.write(resp.content)
        print("Constructed ff_debug.html")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    dump_html()
