import os
import json
import google.generativeai as genai
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.core import config 
from app.utils import prompts 

logger = config.logger

# --- KEY ROTATION MANAGER ---
class MultiKeyManager:
    def __init__(self, keys: List[str]):
        self.keys = keys
        self.current_index = 0
    
    def get_current_key(self) -> str:
        if not self.keys: return ""
        return self.keys[self.current_index]
    
    def switch_key(self) -> str:
        if not self.keys: return ""
        self.current_index = (self.current_index + 1) % len(self.keys)
        new_key = self.keys[self.current_index]
        logger.warning(f"🔄 Switching API Key -> ...{new_key[-4:]}")
        return new_key

key_manager = MultiKeyManager(config.GEMINI_API_KEYS)

# Config ban đầu
if not key_manager.get_current_key():
    raise ValueError("❌ Missing GEMINI_API_KEYS in config")

genai.configure(api_key=key_manager.get_current_key())

MODEL_NAME = 'gemini-2.5-flash-lite' 

response_schema = {
     "type": "OBJECT",
     "properties": {
         "headline": {"type": "STRING"},
         "sentiment_score": {"type": "NUMBER"},
         "trend": {"type": "STRING"},
         "bullet_points": {"type": "ARRAY", "items": {"type": "STRING"}},
         "conclusion": {"type": "STRING"},
     },
     "required": ["headline", "sentiment_score", "trend", "bullet_points", "conclusion"]
}

generation_config = {
    "temperature": 0.4, 
    "response_mime_type": "application/json",
    "response_schema": response_schema
}

def get_model():
    """Helper để lấy model (có thể re-init nếu cần)"""
    try:
        return genai.GenerativeModel(MODEL_NAME, generation_config=generation_config)
    except Exception as e:
        logger.warning(f"⚠️ Fallback to gemini-1.5-pro due to: {e}")
        return genai.GenerativeModel('gemini-1.5-pro', generation_config=generation_config)

def generate_with_retry(prompt: str, retries: int = 3) -> Optional[str]:
    """Hàm bọc gọi API với cơ chế Retry & Rotate Key"""
    attempt = 0
    while attempt < retries:
        try:
            model = get_model()
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            error_msg = str(e).lower()
            # Check lỗi Quota (429) hoặc lỗi Model quá tải
            if "429" in error_msg or "quota" in error_msg or "overloaded" in error_msg:
                logger.warning(f"⚠️ Quota Exceeded / Error: {e}")
                # Rotate Key
                new_key = key_manager.switch_key()
                genai.configure(api_key=new_key)
                # Chờ xíu cho chắc
                import time
                time.sleep(1)
            else:
                logger.error(f"❌ Unrecoverable AI Error: {e}")
                return None
            
            attempt += 1
            
    logger.error("❌ Hết lượt thử (Retries Exhausted).")
    return None

def analyze_market(
    articles: List[Dict[str, Any]], 
    technical_data: str = "Không có dữ liệu kỹ thuật.",
    last_report: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    
    if not articles: return None

    logger.info(f"🤖 AI đang phân tích {len(articles)} bài báo...")

    # 1. Chuẩn bị dữ liệu
    news_text = ""
    for i, art in enumerate(articles, 1):
        content = art.get('content', '') or art.get('summary', '') or ''
        content_clean = content.replace('"', "'").replace('\n', ' ').strip()
        if len(content_clean) > 10000: content_clean = content_clean[:10000] + "..."
        
        news_text += f"""
        <article id="{i}">
            <source>{art.get('source', 'N/A')}</source>
            <title>{art.get('title', 'No Title')}</title>
            <content>{content_clean}</content>
            <date>{art.get('published_at', 'N/A')}</date>
        </article>
        """

    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Xử lý Context Memory
    if last_report:
        prev_context_str = f"""
        - Thời gian report trước: {last_report.get('created_at', 'N/A')}
        - Xu hướng (Trend): {last_report.get('trend', 'N/A')}
        - Điểm Sentiment: {last_report.get('sentiment_score', 0)}
        - Tóm tắt nội dung cũ: {last_report.get('report_content', '')[:300]}...
        """
    else:
        prev_context_str = "Chưa có dữ liệu phiên trước (Đây là phiên chạy đầu tiên)."

    # 2. Prompt Tối ưu
    prompt = prompts.ANALYSIS_PROMPT.format(
        current_time=current_time_str,
        technical_data=technical_data,
        previous_context=prev_context_str,
        news_text=news_text
    )

    # 3. Gọi AI với Retry Mechanism
    try:
        response_text = generate_with_retry(prompt)
        if not response_text: return None
        
        # Xử lý kết quả
        try:
            result_json = json.loads(response_text)
        except json.JSONDecodeError:
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
            result_json = json.loads(clean_text)

        # Validate keys
        required_keys = ["headline", "sentiment_score", "trend", "bullet_points", "conclusion"]
        for key in required_keys:
            if key not in result_json:
                result_json[key] = "N/A" if key != "sentiment_score" else 0

        return result_json

    except Exception as e:
        logger.error(f"❌ Lỗi AI Analysis: {e}")
        return None

def check_breaking_news(content: str) -> Optional[Dict[str, Any]]:
    """
    Kiểm tra xem tin tức có phải là BREAKING NEWS không.
    Trả về: JSON {is_breaking: bool, score: float, headline: str}
    """
    prompt = prompts.BREAKING_NEWS_PROMPT.format(
        content=content[:3000]
    )
    
    try:
        # Dùng model Flash cho nhanh và rẻ
        # Gọi qua generate_with_retry
        response_text = generate_with_retry(prompt)
        if not response_text: return None

        text = response_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        
        # Validate data
        return {
            "is_breaking": data.get("is_breaking", False),
            "score": data.get("score", 0),
            "headline": data.get("headline", "Breaking News")
        }
    except Exception as e:
        logger.error(f"❌ Lỗi Check Breaking News: {e}")
        return None
