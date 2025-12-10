import os
import json
import google.generativeai as genai
from typing import List, Dict, Any, Optional
import config # <--- Import config

# Load API Key
if not config.GEMINI_API_KEY:
    config.logger.error("❌ Chưa cấu hình GEMINI_API_KEY trong file .env hoặc config.py")
    raise ValueError("Missing GEMINI_API_KEY")

genai.configure(api_key=config.GEMINI_API_KEY)

MODEL_NAME = 'gemini-2.5-flash'
logger = config.logger

# --- ĐỊNH NGHĨA CẤU TRÚC JSON MONG MUỐN (SCHEMA) ---
response_schema = {
    "type": "OBJECT",
    "properties": {
        "headline": {"type": "STRING"},
        "sentiment_score": {"type": "NUMBER"},
        "trend": {"type": "STRING"},
        "bullet_points": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        },
        "conclusion": {"type": "STRING"},
        "report_content": {"type": "STRING"}
    },
    "required": ["headline", "sentiment_score", "trend", "bullet_points", "conclusion"]
}

generation_config = {
    "temperature": 0.5,
    "response_mime_type": "application/json",
    "response_schema": response_schema
}

try:
    model = genai.GenerativeModel(MODEL_NAME, generation_config=generation_config)
except Exception as e:
    logger.warning(f"⚠️ Lỗi khởi tạo model {MODEL_NAME}: {e}. Chuyển sang gemini-pro.")
    model = genai.GenerativeModel('gemini-pro')

def analyze_market(articles: List[Dict[str, Any]], last_report: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if not articles: return None

    logger.info(f"🤖 AI đang đọc và phân tích {len(articles)} bài báo...")

    # 1. Chuẩn bị dữ liệu
    news_text = ""
    for i, art in enumerate(articles, 1):
        content_clean = art.get('content', '').replace('"', "'").replace('\n', ' ')[:3000]
        news_text += f"--- BÀI {i} ---\nNguồn: {art.get('source', 'N/A')}\nTiêu đề: {art.get('title', 'No Title')}\nNội dung: {content_clean}\n\n"

    # 2. Xây dựng Prompt
    prompt = f"""
    Bạn là một Chiến lược gia FX cao cấp (Senior Strategist) chuyên về cặp XAU/USD (Gold).
    Phong cách của bạn: "Sniper" - Ngắn gọn, súc tích, đi thẳng vào trọng tâm, không lan man.
    
    TIN TỨC:
    {news_text}
    
    NHIỆM VỤ PHÂN TÍCH:
    1. Tổng hợp tin tức để tìm ra "Key Drivers" (Yếu tố dẫn dắt thị trường: Fed, Chiến tranh, Lạm phát...).
    2. Kết hợp với dữ liệu Kỹ thuật (Fibo, Cản) để đưa ra chiến lược hợp lý nhất.
    3. Chấm điểm Sentiment (-10 Bearish đến +10 Bullish).

    YÊU CẦU OUTPUT (JSON TIẾNG VIỆT):
    - headline: Một câu giật tít cực ngắn (dưới 15 từ), kèm icon cảm xúc. Ví dụ: "🔥 CPI Mỹ tăng nóng, Vàng thủng đáy 2600!"
    - trend: "BULLISH 🟢", "BEARISH 🔴", hoặc "SIDEWAY 🟡".
    - sentiment_score: Số thực (ví dụ: -7.5).
    - bullet_points: Mảng chứa đúng 3 ý chính quan trọng nhất giải thích cho xu hướng. Mỗi ý bắt đầu bằng động từ mạnh. Ngắn gọn (dưới 20 từ/ý).
    - conclusion: Lời khuyên trading hành động (Actionable). Ví dụ: "Canh Sell quanh vùng Fibo 0.5 (2650), SL 2660." (Phải nhắc đến mức giá nếu có trong dữ liệu kỹ thuật).
    
    Lưu ý: Dịch thuật ngữ tài chính sang tiếng Việt chuẩn.
    """

    try:
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
        result_json = json.loads(raw_text)
        
        # --- KIỂM TRA LẠI KEY LẦN CUỐI ---
        if "sentiment_score" not in result_json:
             logger.warning("AI returns missing keys, applying fallback.")
             result_json["sentiment_score"] = result_json.get("score", 0)
             result_json["trend"] = result_json.get("market_trend", "Neutral")
             result_json["report_content"] = result_json.get("content", "Lỗi nội dung")
             
        return result_json

    except Exception as e:
        logger.error(f"❌ Lỗi AI: {e}")
        # Log safe response content
        if 'response' in locals():
             logger.debug(f"Raw response: {response.text}")
        return None