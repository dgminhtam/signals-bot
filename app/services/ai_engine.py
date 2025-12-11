import os
import json
import google.generativeai as genai
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.core import config 
from app.utils import prompts 

logger = config.logger

# Load API Key
if not getattr(config, 'GEMINI_API_KEY', None):
    # Dùng getattr để tránh lỗi nếu file config thiếu biến
    raise ValueError("❌ Missing GEMINI_API_KEY in config")

genai.configure(api_key=config.GEMINI_API_KEY)

# 1. SỬA TÊN MODEL CHUẨN (Flash 1.5 rẻ và context rộng)
MODEL_NAME = 'gemini-2.5-flash-lite' 

# Schema giữ nguyên
response_schema = {
    "type": "OBJECT",
    "properties": {
        "headline": {"type": "STRING"},
        "sentiment_score": {"type": "NUMBER"},
        "trend": {"type": "STRING"},
        "bullet_points": {"type": "ARRAY", "items": {"type": "STRING"}},
        "conclusion": {"type": "STRING"},
        # Bỏ report_content nếu không cần thiết để tiết kiệm token output, 
        # hoặc giữ lại nếu muốn bài viết dài.
    },
    "required": ["headline", "sentiment_score", "trend", "bullet_points", "conclusion"]
}

generation_config = {
    "temperature": 0.4, # Giảm xuống 0.4 để bớt sáng tạo linh tinh, tập trung phân tích
    "response_mime_type": "application/json",
    "response_schema": response_schema
}

try:
    model = genai.GenerativeModel(MODEL_NAME, generation_config=generation_config)
except Exception as e:
    logger.warning(f"⚠️ Lỗi khởi tạo model {MODEL_NAME}: {e}. Fallback to gemini-1.5-pro.")
    model = genai.GenerativeModel('gemini-1.5-pro', generation_config=generation_config)

def analyze_market(
    articles: List[Dict[str, Any]], 
    technical_data: str = "Không có dữ liệu kỹ thuật." # <--- THÊM PARAM NÀY
) -> Optional[Dict[str, Any]]:
    
    if not articles: return None

    logger.info(f"🤖 AI đang phân tích {len(articles)} bài báo...")

    # 1. Chuẩn bị dữ liệu
    # Tăng giới hạn ký tự vì Gemini 1.5 Flash chịu được 1M token. 
    # Cắt 3000 là quá lãng phí context. Tăng lên 15000 hoặc bỏ cắt.
    news_text = ""
    for i, art in enumerate(articles, 1):
        content = art.get('content', '') or art.get('summary', '') or ''
        # Làm sạch cơ bản
        content_clean = content.replace('"', "'").replace('\n', ' ').strip()
        # Chỉ cắt nếu quá dài (ví dụ > 10000 ký tự mỗi bài)
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

    # 2. Prompt Tối ưu
    prompt = prompts.ANALYSIS_PROMPT.format(
        current_time=current_time_str,
        technical_data=technical_data,
        news_text=news_text
    )

    try:
        response = model.generate_content(prompt)
        
        # Xử lý kết quả
        try:
            result_json = json.loads(response.text)
        except json.JSONDecodeError:
            # Gemini Flash đôi khi trả về markdown ```json ... ``` dù đã set mime_type
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            result_json = json.loads(clean_text)

        # Validate keys (Logic cũ của bạn tốt rồi)
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
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
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
