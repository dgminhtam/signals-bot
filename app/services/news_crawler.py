import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from dateutil import parser
import re
import time
import json
from urllib.parse import urljoin
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

def get_full_content(url: str, selector: str = None) -> str:
    """Lấy nội dung bài viết full, hỗ trợ selector động"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200: 
            return "Lỗi truy cập (Chặn Bot)"
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        paragraphs = []
        # 1. Dùng Selector nếu có cấu hình
        if selector:
            paragraphs = soup.select(selector)
        
        # 2. Fallback: Tự động đoán nếu chưa tìm thấy
        if not paragraphs:
            # CMS Detection Fallback (Legacy)
            if "cnn.com" in url:
                paragraphs = soup.select("div.article__content p")
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
        logger.error(f"⚠️ RSS {url} lỗi: {e}")
        return None

def scrape_website_fallback(source_config: Dict) -> List[Dict]:
    """Cào trực tiếp website nếu RSS lỗi (Dynamic URL)"""
    url = source_config.get("web")
    source_name = source_config.get("name")
    
    if not url:
        return []

    logger.info(f"🔄 Đang kích hoạt Web Scraping cho {source_name} ({url})...")
    entries = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Heuristic: Tìm tất cả thẻ A có text đủ dài
        links = soup.find_all('a', href=True)
        seen_titles = set()
        
        for a in links:
            title = a.get_text().strip()
            href = a['href']
            
            # Lọc rác
            if len(title) < 20: continue
            if "javascript:" in href or "mailto:" in href: continue
             
            # Chuẩn hóa URL dynamic bằng urljoin
            full_link = urljoin(url, href)
            
            # Chỉ lấy tin có keyword
            if not check_keywords(title):
                continue
                
            if title in seen_titles: continue
            seen_titles.add(title)

            entries.append({
                "title": title,
                "link": full_link,
                "summary": "",
                "published": datetime.now(timezone.utc).isoformat()
            })
            
        logger.info(f"✅ Web Scraping tìm thấy {len(entries)} bài viết tiềm năng.")
        return entries
        
    except Exception as e:
        logger.error(f"❌ Lỗi Web Scraping {source_name}: {e}")
        return []

def get_gold_news(lookback_minutes: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Quét tin tức từ RSS và Web Fallback.
    Args:
        lookback_minutes: Nếu có, chỉ lấy tin trong khoảng thời gian này.
    Returns:
        List[Dict]: Danh sách các bài viết MỚI vừa được thêm vào DB.
    """
    logger.info(">>> KHỞI TẠO DATABASE...")
    database.init_db() 
    
    logger.info(f">>> ĐANG QUÉT TIN TỨC... (Lookback: {lookback_minutes if lookback_minutes else '24h'})")
    now_utc = datetime.now(timezone.utc)
    
    # Xác định giới hạn thời gian
    if lookback_minutes:
        time_limit = now_utc - timedelta(minutes=lookback_minutes)
    else:
        time_limit = now_utc - timedelta(hours=24) 
    
    new_articles_added = []
    new_articles_count = 0

    for source in config.NEWS_SOURCES:
        entries = []
        is_fallback = False
        source_name = source.get("name", "Unknown")
        rss_url = source.get("rss")
        selector = source.get("selector")
        
        # 1. Thử RSS trước
        try:
            feed = get_rss_feed_data(rss_url)
            if feed and feed.entries:
                entries = feed.entries
                logger.info(f"-> RSS {source_name}: Quét {len(entries)} bài...")
            else:
                raise Exception("RSS Empty/Fail")
        except:
            # 2. RSS Lỗi -> Thử Web Scraping
            logger.warning(f"⚠️ RSS {source_name} thất bại. Chuyển sang Web Scraping...")
            entries = scrape_website_fallback(source)
            is_fallback = True
        
        if not entries:
            continue

        # 3. Xử lý danh sách bài viết (từ RSS hoặc Web)
        for entry in entries:
            # Chuẩn hóa field (feedparser dùng object, scraping dùng dict)
            if isinstance(entry, dict):
                link = entry.get("link", "")
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                pub_str = entry.get("published", "")
            else:
                link = getattr(entry, "link", "")
                title = getattr(entry, "title", "")
                summary = clean_html(getattr(entry, "summary", ""))
                pub_str = getattr(entry, "published", getattr(entry, "updated", ""))

            if not link or not title: continue
            
            # KIỂM TRA TRÙNG
            if database.check_article_exists(link):
                continue

            # Xử lý thời gian (Chỉ check kỹ với RSS, Web scraping lấy tin mới nhất)
            if not is_fallback:
                try:
                    pub_date = parser.parse(pub_str)
                    if pub_date.tzinfo is None: pub_date = pub_date.replace(tzinfo=timezone.utc)
                    if pub_date < time_limit: continue
                except: continue
            else:
                # Với Web Fallback, mặc định tin lấy về là "mới" nếu chưa có trong DB
                # nhưng để an toàn, gán time hiện tại
                pub_date = now_utc

            # Check Keyword (Double check cho chắc chắn)
            matched_kws = check_keywords(title + " " + summary)
            
            if matched_kws:
                logger.info(f"   [+] Tin mới ({'WEB' if is_fallback else 'RSS'}): {title[:50]}...")
                
                # Truyền selector vào hàm get_full_content
                full_content = get_full_content(link, selector=selector)
                
                news_item = {
                    "id": link,
                    "source": source_name,
                    "published_at": pub_date.isoformat(),
                    "title": title,
                    "keywords": matched_kws,
                    "url": link,
                    "content": full_content
                }
                
                if database.save_to_db(news_item):
                    new_articles_count += 1
                    new_articles_added.append(news_item)
                
                time.sleep(1) # Delay nhẹ

    logger.info("="*60)
    logger.info(f"✅ HOÀN TẤT! Đã thêm {new_articles_count} bài viết mới vào Database.")
    logger.info("="*60)
    return new_articles_added
