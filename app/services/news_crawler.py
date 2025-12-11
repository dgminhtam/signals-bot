import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from dateutil import parser
import re
import time
import json
from typing import List, Dict, Optional, Any
from app.core import config
from app.core import database # Updated import

logger = config.logger
KEYWORDS = {
    "DIRECT": config.KEYWORDS_DIRECT,
    "CORRELATION": config.KEYWORDS_CORRELATION
}
HEADERS = config.HEADERS

def clean_html(raw_html: str) -> str:
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()

def check_keywords(text: str) -> List[str]:
    found_keywords = []
    text_lower = text.lower()
    all_keywords = KEYWORDS["DIRECT"] + KEYWORDS["CORRELATION"]
    for kw in all_keywords:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, text_lower):
            found_keywords.append(kw)
    return list(set(found_keywords)) # Loại bỏ keyword trùng lặp

def get_full_content(url: str) -> str:
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200: 
            return "Lỗi truy cập (Chặn Bot)"
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        if "kitco.com" in url:
            paragraphs = soup.select("div.article-body p")
        elif "investing.com" in url:
            paragraphs = soup.select("div.WYSIWYG p")
        else:
            paragraphs = soup.find_all('p')
            
        full_text = "\\n\\n".join([p.get_text().strip() for p in paragraphs])
        return full_text if len(full_text) > 200 else "Nội dung quá ngắn/bị ẩn."
    except Exception as e:
        return f"Lỗi cào dữ liệu: {e}"

def get_rss_feed_data(url: str):
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return feedparser.parse(response.content)
    except Exception as e:
        logger.error(f"Lỗi tải RSS {url}: {e}")
        return None

def get_gold_news(lookback_minutes: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Quét tin tức từ RSS.
    Args:
        lookback_minutes: Nếu có, chỉ lấy tin trong khoảng thời gian này (dùng cho Alert Worker).
                          Nếu None, lấy tin trong 24h qua (dùng cho Daily Report).
    Returns:
        List[Dict]: Danh sách các bài viết MỚI vừa được thêm vào DB.
    """
    logger.info(">>> KHỞI TẠO DATABASE...")
    database.init_db() # 1. Tạo bảng nếu chưa có
    
    logger.info(f">>> ĐANG QUÉT TIN TỨC... (Lookback: {lookback_minutes if lookback_minutes else '24h'})")
    now_utc = datetime.now(timezone.utc)
    
    if lookback_minutes:
        time_limit = now_utc - timedelta(minutes=lookback_minutes)
    else:
        time_limit = now_utc - timedelta(hours=24) 
    
    new_articles_added = []
    new_articles_count = 0

    for source in config.RSS_SOURCES:
        try:
            feed = get_rss_feed_data(source["url"])
            if not feed or not feed.entries:
                logger.warning(f"-> {source['name']}: Không lấy được dữ liệu.")
                continue

            logger.info(f"-> {source['name']}: Quét {len(feed.entries)} bài...")
            
            for entry in feed.entries:
                link = entry.get("link", "")
                
                # 2. KIỂM TRA TỒN TẠI TRƯỚC
                if database.check_article_exists(link):
                    continue

                # Xử lý ngày tháng
                published = entry.get("published", entry.get("updated", ""))
                if not published: continue
                try:
                    pub_date = parser.parse(published)
                    if pub_date.tzinfo is None: pub_date = pub_date.replace(tzinfo=timezone.utc)
                    if pub_date < time_limit: continue
                except: continue

                title = entry.get("title", "")
                summary = clean_html(entry.get("summary", ""))
                
                # Check Keyword
                matched_kws = check_keywords(title + " " + summary)
                
                if matched_kws:
                    logger.info(f"   [+] Tin mới: {title[:50]}...")
                    
                    full_content = get_full_content(link)
                    
                    news_item = {
                        "id": link,
                        "source": source["name"],
                        "published_at": pub_date.isoformat(),
                        "title": title,
                        "keywords": matched_kws,
                        "url": link,
                        "content": full_content
                    }
                    
                    # 3. LƯU VÀO DB
                    if database.save_to_db(news_item):
                        new_articles_count += 1
                        new_articles_added.append(news_item)
                    time.sleep(1) # Delay nhẹ
            
        except Exception as e:
            logger.error(f"Lỗi nguồn {source['name']}: {e}")

    logger.info("="*60)
    logger.info(f"✅ HOÀN TẤT! Đã thêm {new_articles_count} bài viết mới vào Database.")
    logger.info("="*60)
    return new_articles_added
