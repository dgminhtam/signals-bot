import feedparser
import asyncio
import re
import time
import random
import json
from datetime import datetime, timedelta, timezone
from dateutil import parser
from urllib.parse import urljoin
from typing import List, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor

from app.core import config
from app.core import database

# --- Import & Check Dependencies ---
try:
    from curl_cffi.requests import AsyncSession
except ImportError:
    AsyncSession = None
    config.logger.warning("Thư viện 'curl_cffi' chưa được cài đặt. (pip install curl_cffi)")

try:
    from newspaper import Article, Source
    import newspaper
except ImportError:
    Article = None
    Source = None
    newspaper = None
    config.logger.warning("Thư viện 'newspaper3k' chưa được cài đặt. (pip install newspaper3k lxml_html_clean)")

logger = config.logger
KEYWORDS = {
    "DIRECT": config.KEYWORDS_DIRECT,
    "CORRELATION": config.KEYWORDS_CORRELATION
}

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
    return list(set(found_keywords))

# --- Async Helper Functions ---

async def fetch_url(url: str, timeout: int = 30) -> Optional[Any]:
    """
    Async helper fetch data with rotation of impersonations.
    Returns: Response object or None
    """
    if not AsyncSession:
        return None

    browsers = ["chrome120", "chrome110", "safari15_5"]
    
    for browser in browsers:
        try:
            logger.info(f"🌐 Fetching {url} (Impersonate: {browser})...")
            
            # Sử dụng AsyncSession context manager
            async with AsyncSession(
                impersonate=browser, 
                timeout=timeout,
                headers={"Referer": "https://www.google.com/"}
            ) as session:
                response = await session.get(url)
            
            if response.status_code == 200:
                return response
            elif response.status_code == 404:
                logger.warning(f"❌ 404 Not Found: {url}")
                return None
            else:
                logger.warning(f"⚠️ Status {response.status_code} with {browser}. Retrying next in 5s...")
                await asyncio.sleep(5)
                
        except Exception as e:
            logger.warning(f"⚠️ Network error with {browser}: {e}. Retrying next in 5s...")
            await asyncio.sleep(5)
            
    logger.error(f"❌ Failed to fetch {url} after all attempts.")
    return None

def _parse_article_sync(url: str, html_content: str) -> Dict[str, str]:
    """Hàm đồng bộ để parse article bằng newspaper3k"""
    if not Article:
        return {}
    try:
        article = Article(url)
        article.set_html(html_content)
        article.parse()
        return {
            "text": article.text.strip(),
            "image": article.top_image
        }
    except Exception as e:
        logger.error(f"Newspaper parse error: {e}")
        return {}

async def get_full_content(url: str, selector: str = None) -> Dict[str, str]:
    """
    Lấy nội dung bài viết full (Async).
    """
    error_res = {"content": "", "image_url": ""}
    
    if not AsyncSession or not Article:
        error_res["content"] = "Lỗi: Thiếu thư viện curl_cffi hoặc newspaper3k."
        return error_res

    response = await fetch_url(url)
    if not response:
        error_res["content"] = "Lỗi kết nối (Network/Blocked)."
        return error_res
        
    try:
        # Chạy parsing (CPU-bound) trong executor
        loop = asyncio.get_running_loop()
        parse_result = await loop.run_in_executor(
            None, 
            lambda: _parse_article_sync(url, response.text)
        )
        
        full_text = parse_result.get("text", "")
        top_image = parse_result.get("image", None)
        
        if len(full_text) > 100:
            return {"content": full_text, "image_url": top_image}
        else:
            error_res["content"] = "Nội dung quá ngắn/bị ẩn (Newspaper parse failed)."
            return error_res

    except Exception as e:
        logger.error(f"❌ Error getting full content for {url}: {e}")
        error_res["content"] = f"Lỗi cào dữ liệu: {e}"
        return error_res

def _parse_rss_sync(content: bytes):
    return feedparser.parse(content)

async def get_rss_feed_data(url: str, timeout: int = 30):
    """Lấy dữ liệu RSS (Async)"""
    try:
        response = await fetch_url(url, timeout=timeout)
        if not response:
             return None
             
        # Parse content trong executor
        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(None, lambda: _parse_rss_sync(response.content))
        return feed

    except Exception as e:
        logger.error(f"⚠️ RSS {url} lỗi: {e}")
        return None

def _scrape_fallback_sync(url: str, html_content: str) -> List[Dict]:
    """Logic parse fallback dùng newspaper.Source (Sync)"""
    if not newspaper: return []
    entries = []
    seen_titles = set()
    try:
        source = newspaper.Source(url)
        source.html = html_content
        source.parse()
        
        if not source.articles:
             return []
             
        for article in source.articles:
            href = article.url
            if not href: continue
            
            # Ở đây không gọi check_keywords (để logic đó ở ngoài hoặc truyền vào nếu cần)
            # Tạm thời chỉ extract URL thô, lọc sau
            
            fake_title = href.split('/')[-1].replace('-', ' ').title()
            if len(fake_title) < 10: continue
            if href in seen_titles: continue
            seen_titles.add(href)
            
            entries.append({
                "title": fake_title,
                "link": href,
                "summary": "",
                "published": datetime.now(timezone.utc).isoformat()
            })
        return entries
    except Exception as e:
        logger.error(f"Fallback parse error: {e}")
        return []

async def scrape_website_fallback(source_config: Dict) -> List[Dict]:
    """Cào trực tiếp website nếu RSS lỗi (Async)"""
    url = source_config.get("web")
    source_name = source_config.get("name")
    
    if not url:
        return []

    logger.info(f"🔄 Đang kích hoạt Web Scraping cho {source_name} ({url})...")
    
    try:
        response = await fetch_url(url)
        if not response:
            return []

        # Run parsing in executor
        loop = asyncio.get_running_loop()
        entries = await loop.run_in_executor(
            None, 
            lambda: _scrape_fallback_sync(url, response.text)
        )
        
        # Lọc keywords ở đây (CPU bound nhẹ, có thể để ở main thread async cũng được)
        filtered_entries = []
        for entry in entries:
             # Logic lọc keyword cho link
             if len(check_keywords(entry['link'])) > 0:
                 filtered_entries.append(entry)
        
        logger.info(f"✅ Web Scraping (Newspaper Source) tìm thấy {len(filtered_entries)} bài viết tiềm năng.")
        return filtered_entries
        
    except Exception as e:
        logger.error(f"❌ Lỗi Web Scraping {source_name}: {e}")
        return []

async def get_gold_news(lookback_minutes: Optional[int] = None, fast_mode: bool = False) -> List[Dict[str, Any]]:
    """
    Quét tin tức từ RSS và Web Fallback (Async).
    """
    logger.debug(">>> KHỞI TẠO DATABASE...")
    # Init DB Async
    await database.init_db()
    
    logger.debug(f">>> ĐANG QUÉT TIN TỨC... (Lookback: {lookback_minutes if lookback_minutes else '24h'})")
    now_utc = datetime.now(timezone.utc)
    
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

        # 1. Thử RSS
        try:
            feed = await get_rss_feed_data(rss_url, timeout=timeout_cfg)
            if feed and feed.entries:
                entries = feed.entries
                logger.debug(f"-> RSS {source_name}: Quét {len(entries)} bài...")
            else:
                raise Exception("RSS Empty/Fail")
        except:
            # 2. Web Scraping Fallback
            if not fast_mode:
                logger.warning(f"⚠️ RSS {source_name} thất bại. Chuyển sang Web Scraping...")
                entries = await scrape_website_fallback(source)
                is_fallback = True
            else:
                 logger.warning(f"⚠️ RSS {source_name} thất bại. Skip Web Scraping (Fast Mode).")
        
        if not entries:
            continue

        # 3. Xử lý bài viết
        for entry in entries:
            # Chuẩn hóa (feedparser obj hoặc dict)
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
            
            # DB Check: Async call
            exists = await database.check_article_exists(link)
            if exists:
                continue

            # Check time
            if not is_fallback:
                try:
                    pub_date = parser.parse(pub_str)
                    if pub_date.tzinfo is None: pub_date = pub_date.replace(tzinfo=timezone.utc)
                    if pub_date < time_limit: continue
                except: continue
            else:
                pub_date = now_utc

            # Check Keyword
            matched_kws = check_keywords(title + " " + summary)
            
            if matched_kws:
                logger.info(f"   [+] Tin mới ({'WEB' if is_fallback else 'RSS'}): {title[:50]}...")
                
                # Fetch Full Content Async
                extract_res = await get_full_content(link, selector=selector)
                full_content = extract_res.get("content", "")
                image_url = extract_res.get("image_url")
                
                is_error_content = isinstance(full_content, str) and (full_content.strip().startswith("Lỗi") or full_content.strip().startswith("Error"))
                is_too_short = len(full_content) < 200

                if is_error_content or is_too_short:
                    logger.warning(f"⚠️ Content invalid or too short. Skipping DB save.")
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
                
                # DB Save: Async call
                saved = await database.save_to_db(news_item)
                if saved:
                    new_articles_count += 1
                    new_articles_added.append(news_item)
                
                # Async Sleep
                if not fast_mode:
                    sleep_time = random.uniform(3, 6)
                    logger.debug(f"   ...Sleeping {sleep_time:.1f}s...")
                    await asyncio.sleep(sleep_time)

    logger.info("="*60)
    logger.info(f"✅ HOÀN TẤT! Đã thêm {new_articles_count} bài viết mới vào Database.")
    logger.info("="*60)
    return new_articles_added
