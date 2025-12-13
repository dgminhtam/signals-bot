"""
WordPress Service - Tự động đăng bài lên WordPress qua REST API
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Dict, Any
import logging
import markdown
from app.core import config

logger = config.logger

class WordPressService:
    def __init__(self):
        self.url = config.WORDPRESS_URL
        self.user = config.WORDPRESS_USER
        self.password = config.WORDPRESS_APP_PASSWORD
        self.timeout = 30  # 30 seconds timeout
        
        if not all([self.url, self.user, self.password]):
            logger.warning("⚠️ WordPress config chưa đầy đủ. Tính năng post WP sẽ bị tắt.")
            self.enabled = False
        else:
            self.enabled = True
            self.auth = (self.user, self.password)
            self.headers = {"Content-Type": "application/json"}
            
            # Setup Session with Retry strategy
            self.session = requests.Session()
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT"]
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)
            self.session.auth = self.auth
    
    def upload_image(self, file_path: str, title: str = "Chart Image") -> Optional[int]:
        """
        Upload ảnh lên WordPress Media Library
        Returns: Media ID nếu thành công, None nếu lỗi
        """
        if not self.enabled:
            return None
            
        try:
            endpoint = f"{self.url}/wp-json/wp/v2/media"
            
            with open(file_path, 'rb') as img:
                files = {
                    'file': (file_path.split('/')[-1], img, 'image/png')
                }
                
                # Note: Session auth is applied automatically
                response = self.session.post(
                    endpoint,
                    files=files,
                    headers={'Content-Disposition': f'attachment; filename="{title}.png"'},
                    timeout=self.timeout
                )
            
            if response.status_code in [200, 201]:
                media_id = response.json().get('id')
                logger.info(f"✅ Đã upload ảnh lên WordPress. Media ID: {media_id}")
                return media_id
            else:
                logger.error(f"❌ Lỗi upload ảnh WP: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Exception khi upload ảnh WP: {e}")
            return None
    
    def convert_telegram_to_html(self, telegram_content: str) -> str:
        """
        Chuyển đổi nội dung Telegram (Markdown-style) sang HTML cho WordPress
        """
        try:
            # Basic markdown conversion
            html_content = markdown.markdown(
                telegram_content,
                extensions=['nl2br', 'markdown.extensions.tables']
            )
            
            # Additional formatting for WordPress
            html_content = html_content.replace('**', '<strong>').replace('**', '</strong>')
            html_content = html_content.replace('__', '<em>').replace('__', '</em>')
            
            return html_content
        except Exception as e:
            logger.error(f"❌ Lỗi convert Markdown->HTML: {e}")
            return telegram_content  # Fallback to original
    
    def create_post(
        self, 
        title: str, 
        content: str, 
        media_id: Optional[int] = None,
        status: str = "draft"
    ) -> Optional[Dict[str, Any]]:
        """
        Tạo bài viết WordPress
        Args:
            title: Tiêu đề bài viết
            content: Nội dung (Telegram format sẽ được convert sang HTML)
            media_id: ID của ảnh featured (optional)
            status: 'draft' hoặc 'publish'
        Returns: Post data nếu thành công, None nếu lỗi
        """
        if not self.enabled:
            return None
        
        try:
            endpoint = f"{self.url}/wp-json/wp/v2/posts"
            
            # Convert content to HTML
            html_content = self.convert_telegram_to_html(content)
            
            # Chuẩn bị payload
            post_data = {
                "title": title,
                "content": html_content,
                "status": status,
                "format": "standard"
            }
            
            # Thêm featured image nếu có
            if media_id:
                post_data["featured_media"] = media_id
            
            response = self.session.post(
                endpoint,
                headers=self.headers,
                json=post_data,
                timeout=self.timeout
            )
            
            if response.status_code in [200, 201]:
                post_info = response.json()
                post_id = post_info.get('id')
                post_link = post_info.get('link')
                logger.info(f"✅ Đã tạo bài viết WP (ID: {post_id}, Status: {status})")
                logger.info(f"🔗 Link: {post_link}")
                return post_info
            else:
                logger.error(f"❌ Lỗi tạo post WP: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Exception khi tạo post WP: {e}")
            return None
    
    def create_liveblog_entry(
        self,
        title: str,
        content: str,
        image_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Tạo Liveblog Entry (elb_entry) - Verified by cURL
        Args:
            title: Headline
            content: Nội dung HTML
            image_url: Optional image
        """
        if not self.enabled:
            return None
        
        try:
            # Endpoint chuẩn từ cURL (wp/v2/elb_entry)
            endpoint = f"{self.url}/wp-json/wp/v2/elb_entry"
            
            # Convert Telegram markdown -> HTML
            html_content = self.convert_telegram_to_html(content)
            
            # Embed image nếu có
            if image_url:
                html_content = f'<img src="{image_url}" alt="Chart" style="max-width:100%; height:auto;"><br><br>' + html_content
            
            # Payload theo cURL đã verify
            entry_data = {
                "title": title,
                "content": html_content,
                "status": "publish",
                "meta": {
                    "_elb_liveblog": config.WORDPRESS_LIVEBLOG_ID,  # Link bài gốc
                    "_elb_status": "open"
                }
            }
            
            response = self.session.post(
                endpoint,
                headers=self.headers,
                json=entry_data,
                timeout=self.timeout
            )
            
            if response.status_code in [200, 201]:
                entry_info = response.json()
                entry_id = entry_info.get('id')
                logger.info(f"✅ Đã tạo Liveblog Entry (ID: {entry_id})")
                return entry_info
            else:
                logger.error(f"❌ Lỗi tạo liveblog entry: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Exception khi tạo liveblog entry: {e}")
            return None

# Singleton instance
wordpress_service = WordPressService()
