
import logging
import sys
import os
# Thêm thư mục gốc vào sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import news_crawler

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("TestInvesting")

def test_fetch():
    # URL provided by user
    url_fail = "https://www.investing.com/news/stock-market-news/chinas-cmoc-to-buy-equinox-gold-mines-in-brazil-for-over-1-bln-4407162"
    
    print(f">>> Testing fetch for: {url_fail}")
    content = news_crawler.get_full_content(url_fail)
    print(">>> Result Preview:")
    print(content) 
    
    with open("test_invest_res.txt", "w", encoding="utf-8") as f:
        f.write(content)
        
    if "Lỗi" in content or "Nội dung quá ngắn" in content:
        print("!!! FAIL: Content fetch failed.")
    else:
        print(">>> SUCCESS: Content fetched.")

if __name__ == "__main__":
    test_fetch()
