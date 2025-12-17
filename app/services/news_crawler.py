import feedparser
import requests
from datetime import datetime, timedelta, timezone
from dateutil import parser
import re
import time
import random
import json
from urllib.parse import urljoin
from typing import List, Dict, Optional, Any
from app.core import config
from app.core import database

try:
    from curl_cffi import requests as c_requests
except ImportError:
    c_requests = None
    config.logger.warning("Thư viện 'curl_cffi' chưa được cài đặt. (pip install curl_cffi)")

try:
    from newspaper import Article
except ImportError:
    Article = None
    config.logger.warning("Thư viện 'newspaper3k' chưa được cài đặt. (pip install newspaper3k lxml_html_clean)")

logger = config.logger
KEYWORDS = {
    "DIRECT": config.KEYWORDS_DIRECT,
    "CORRELATION": config.KEYWORDS_CORRELATION
}

def clean_html(raw_html: str) -> str:
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()


def fetch_url(url: str, timeout: int = 30) -> Optional[Any]:
    """
    Helper fetch data with rotation of impersonations to bypass TLS Blocking/403.
    Returns: Response object or None
    """
    if not c_requests:
        return None

    # List allow rotation if failed
    browsers = ["chrome120", "chrome110", "safari15_5"]
    
    for browser in browsers:
        try:
            logger.info(f"🌐 Fetching {url} (Impersonate: {browser})...")
            response = c_requests.get(
                url, 
                impersonate=browser, 
                timeout=timeout,
                headers={"Referer": "https://www.google.com/"}
            )
            
            if response.status_code == 200:
                return response
            elif response.status_code == 404:
                logger.warning(f"❌ 404 Not Found: {url}")
                return None # No need to retry 404
            else:
                logger.warning(f"⚠️ Status {response.status_code} with {browser}. Retrying next in 5s...")
                time.sleep(5)
                
        except Exception as e:
            logger.warning(f"⚠️ Network error with {browser}: {e}. Retrying next in 5s...")
            time.sleep(5)
            
    logger.error(f"❌ Failed to fetch {url} after all attempts.")
    return None

def check_keywords(text: str) -> List[str]:
    found_keywords = []
    text_lower = text.lower()
    all_keywords = KEYWORDS["DIRECT"] + KEYWORDS["CORRELATION"]
    for kw in all_keywords:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, text_lower):
            found_keywords.append(kw)
    return list(set(found_keywords))

def get_full_content(url: str, selector: str = None) -> Dict[str, str]:
    """
    Lấy nội dung bài viết full sử dụng curl_cffi + newspaper3k.
    Returns: Dict {"content": str, "image_url": str}
    """
    error_res = {"content": "", "image_url": ""}
    
    if not c_requests or not Article:
        error_res["content"] = "Lỗi: Thiếu thư viện curl_cffi hoặc newspaper3k."
        return error_res

    response = fetch_url(url)
    if not response:
        error_res["content"] = "Lỗi kết nối (Network/Blocked)."
        return error_res
        
    try:
        # Bước 2: Parsing - Dùng newspaper3k phân tích HTML
        article = Article(url)
        article.set_html(response.text) # Nạp HTML đã download (đã bypass TLS)
        article.parse()
        
        full_text = article.text.strip()
        top_image = article.top_image
        
        # Bước 3: Extraction Result
        if len(full_text) > 100:
            return {"content": full_text, "image_url": top_image}
        else:
            # Fallback debug
            error_res["content"] = "Nội dung quá ngắn/bị ẩn (Newspaper parse failed)."
            return error_res

    except Exception as e:
        logger.error(f"❌ Error getting full content for {url}: {e}")
        error_res["content"] = f"Lỗi cào dữ liệu: {e}"
        return error_res


def get_rss_feed_data(url: str, timeout: int = 30):
    """Lấy dữ liệu RSS sử dụng fetch_url helper"""
    try:
        response = fetch_url(url, timeout=timeout)
        if not response:
             return None
             
        # Parse content
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
        # Use fetch_url (handles Chrome/Safari rotation)
        response = fetch_url(url)
        if not response:
            return []

        # Use newspaper3k Source to extract links (Smart discovery)
        # We manually inject HTML to use curl_cffi's bypass
        import newspaper
        source = newspaper.Source(url)
        source.html = response.text
        source.parse() # Parses the HTML to find links
        
        if not source.articles:
             logger.warning(f"Newspaper found 0 articles for {url}")
             return []
             
        seen_titles = set()
        
        for article in source.articles:
            # article.url is available
            # We don't have title yet unless we download/parse, 
            # BUT newspaper sometimes extracts title from link text?
            # actually source.articles usually just has URLs.
            # We need to filter by URL or download to check title?
            # Downloading every article is expensive (slow).
            
            # Optimization: Filter URL string by keywords first?
            # Keywords are usually in the slug.
            
            href = article.url
            if not href: continue
             
            # Keyword check in URL (fast filter)
            # If not in URL, we might skip or have to download.
            # Let's rely on URL Check for speed in fallback mode.
            if not len(check_keywords(href)) > 0:
                 continue

            # If passed URL check, we can assume it's relevant, 
            # OR we can try to fetch title? 
            # Let's just use the URL as title placeholder or try to format it?
            # Validating 100 links by downloading is too slow.
            # Let's check if newspaper extracted any link text?
            # source.articles is a list of Article objects.
            # They don't have link text stored by default logic of Source.parse().
            
            # Alternative: Use BeautifulSoup to get Link Text (User wants to avoid BS4).
            # But Link Text is vital for "Title".
            # URL slug is often enough for title? e.g. /news/gold-price-hits-record
            
            # Let's attempt to format title from URL
            fake_title = href.split('/')[-1].replace('-', ' ').title()
            
            if len(fake_title) < 10: 
                continue
                
            if href in seen_titles: continue
            seen_titles.add(href)
            
            entries.append({
                "title": fake_title, # News crawler will fetch full content anyway and can update title? No.
                # Actually, main logic uses Title for notification.
                # Without real title, it looks ugly.
                "link": href,
                "summary": "",
                "published": datetime.now(timezone.utc).isoformat()
            })
            
        # Re-verify with BS4? No. User wants pure newspaper/no BS4.
        # But using newspaper.Source doesn't give Titles without downloading.
        # This is a trade-off.
        
        # ACTUALLY, strict "newspaper" usage might be worse if we lose Titles.
        # But I can implement it.
        # OR I can check if `newspaper` has a way to keep link text?
        # No easy way in standard API.
        
        # Let's stick to newspaper Source but be aware of the title limitation.
        # I will use the "cleaning URL" method for title.
        
        logger.info(f"✅ Web Scraping (Newspaper Source) tìm thấy {len(entries)} bài viết tiềm năng.")
        return entries
        
    except Exception as e:
        logger.error(f"❌ Lỗi Web Scraping {source_name}: {e}")
        return []

def get_gold_news(lookback_minutes: Optional[int] = None, fast_mode: bool = False) -> List[Dict[str, Any]]:
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
        
        timeout_cfg = 10 if fast_mode else 30

        # 1. Thử RSS trước
        try:
            feed = get_rss_feed_data(rss_url, timeout=timeout_cfg)
            if feed and feed.entries:
                entries = feed.entries
                logger.info(f"-> RSS {source_name}: Quét {len(entries)} bài...")
            else:
                raise Exception("RSS Empty/Fail")
        except:
            # 2. RSS Lỗi -> Thử Web Scraping (Skip in Fast Mode)
            if not fast_mode:
                logger.warning(f"⚠️ RSS {source_name} thất bại. Chuyển sang Web Scraping...")
                entries = scrape_website_fallback(source)
                is_fallback = True
            else:
                 logger.warning(f"⚠️ RSS {source_name} thất bại. Skip Web Scraping (Fast Mode).")
        
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
                extract_res = get_full_content(link, selector=selector)
                full_content = extract_res.get("content", "")
                image_url = extract_res.get("image_url")
                
                # Kiểm tra nội dung hợp lệ
                is_error_content = isinstance(full_content, str) and (full_content.strip().startswith("Lỗi") or full_content.strip().startswith("Error"))
                is_too_short = len(full_content) < 200

                if is_error_content or is_too_short:
                    logger.warning(f"⚠️ Content invalid or too short. Skipping DB save. (Error: {is_error_content}, Short: {is_too_short})")
                    continue

                news_item = {
                    "id": link,
                    "source": source_name,
                    "published_at": pub_date.isoformat(),
                    "title": title,
                    "keywords": matched_kws,
                    "url": link,
                    "content": full_content,
                    "image_url": image_url
                }
                
                if database.save_to_db(news_item):
                    new_articles_count += 1
                    new_articles_added.append(news_item)
                
                # Polite Delay: Random sleep to avoid IP Ban/Rate Limit
                if not fast_mode:
                    sleep_time = random.uniform(3, 6)
                    logger.info(f"   ...Sleeping {sleep_time:.1f}s...")
                    time.sleep(sleep_time)

    logger.info("="*60)
    logger.info(f"✅ HOÀN TẤT! Đã thêm {new_articles_count} bài viết mới vào Database.")
    logger.info("="*60)
    return new_articles_added
