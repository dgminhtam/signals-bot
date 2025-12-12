from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import logging
from app.core import config
from app.utils import prompts
from app.services.ai_base import AIService
from app.services.gemini_service import GeminiService
from app.services.openai_service import OpenAIService
from app.services.groq_service import GroqService

logger = config.logger

# --- FACTORY PATTERN ---
def get_ai_service() -> AIService:
    provider = config.AI_PROVIDER
    logger.info(f"🤖 Initializing AI Provider: {provider.upper()}")
    
    if provider == "gemini":
        return GeminiService()
    elif provider == "openai":
        return OpenAIService()
    elif provider == "groq":
        return GroqService()
    else:
        logger.warning(f"⚠️ Unknown provider '{provider}', falling back to Gemini.")
        return GeminiService()

# Initialize Service Global
ai_service = get_ai_service()

# --- JSON SCHEMAS ---
analysis_schema = {
    "type": "OBJECT",
     "properties": {
          "reasoning": {"type": "STRING", "description": "Chi tiết quy trình tư duy từng bước (CoT)"},
          "headline": {"type": "STRING"},
          "sentiment_score": {"type": "NUMBER"},
          "trend": {"type": "STRING"},
          "bullet_points": {"type": "ARRAY", "items": {"type": "STRING"}},
          "conclusion": {"type": "STRING"},
     },
     "required": ["reasoning", "headline", "sentiment_score", "trend", "bullet_points", "conclusion"]
}

breaking_news_schema = {
    "type": "OBJECT",
     "properties": {
          "is_breaking": {"type": "BOOLEAN"},
          "score": {"type": "NUMBER"},
          "headline": {"type": "STRING"}
     },
     "required": ["is_breaking", "score", "headline"]
}

# --- BUSINESS LOGIC FUNCTIONS ---

def analyze_market(
    articles: List[Dict[str, Any]], 
    technical_data: str = "Không có dữ liệu kỹ thuật.",
    last_report: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    
    if not articles: return None

    logger.info(f"🤖 AI nhận {len(articles)} bài báo...")
    
    # 1. Giới hạn số lượng articles
    MAX_ARTICLES = 10
    if len(articles) > MAX_ARTICLES:
        articles_sorted = sorted(
            articles, 
            key=lambda x: x.get('published_at', ''), 
            reverse=True
        )
        articles = articles_sorted[:MAX_ARTICLES]
        logger.info(f"📊 Giới hạn xuống {MAX_ARTICLES} bài mới nhất.")
    
    logger.info(f"✅ Phân tích {len(articles)} bài báo...")

    # 2. Chuẩn bị dữ liệu
    news_text = ""
    for i, art in enumerate(articles, 1):
        content = art.get('content', '') or art.get('summary', '') or ''
        content_clean = content.replace('"', "'").replace('\n', ' ').strip()
        
        MAX_CONTENT_LENGTH = 5000
        if len(content_clean) > MAX_CONTENT_LENGTH: 
            content_clean = content_clean[:MAX_CONTENT_LENGTH] + "..."
        
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

    # 3. Gọi AI qua Service Factory
    try:
        response_text = ai_service.generate_content(prompt, schema=analysis_schema)
        if not response_text: return None
        
        # Xử lý kết quả JSON
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
    """
    prompt = prompts.BREAKING_NEWS_PROMPT.format(
        content=content[:3000]
    )
    
    try:
        # Sử dụng Breaking News Schema
        response_text = ai_service.generate_content(prompt, schema=breaking_news_schema)
        if not response_text: return None
        
        try:
            result_json = json.loads(response_text)
        except json.JSONDecodeError:
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
            result_json = json.loads(clean_text)
            
        return result_json
        
    except Exception as e:
        logger.error(f"❌ Lỗi Breaking News Check: {e}")
        return None
