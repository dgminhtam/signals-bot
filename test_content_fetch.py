
import logging
from app.services import news_crawler

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("TestContent")

def test_fetch():
    # URL provided by user
    url_fail = "https://www.fxstreet.com/news/usd-inr-continues-its-bull-run-amid-consistent-foreign-outflows-from-india-202512150532"
    
    print(f">>> Testing fetch for: {url_fail}")
    content = news_crawler.get_full_content(url_fail)
    print(">>> Result:")
    print(content)
    
    if "Lỗi" in content or "Nội dung quá ngắn" in content:
        print("!!! FAIL: Content fetch failed.")
    else:
        print(">>> SUCCESS: Content fetched.")

if __name__ == "__main__":
    test_fetch()
