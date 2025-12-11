import json
import os
import datetime
from typing import Dict, Any
from app.core import database
from app.services import ai_engine
from app.services import charter
from app.services import telegram_bot
from app.core import config 

logger = config.logger

def format_telegram_message(data: Dict[str, Any]) -> str:
    """
    Hàm làm đẹp tin nhắn Telegram (Formatter) - Optimized UI
    """
    # 1. Lấy dữ liệu an toàn
    headline = data.get('headline', 'BẢN TIN THỊ TRƯỜNG').upper()
    trend = data.get('trend', 'NEUTRAL')
    score = data.get('sentiment_score', 0)
    bullets = data.get('bullet_points', [])
    conclusion = data.get('conclusion', 'Dữ liệu đang cập nhật...')

    # 2. Xử lý Icon & Màu sắc Trend
    trend_upper = trend.upper()
    if "BULLISH" in trend_upper:
        trend_display = "🚀 ĐÀ TĂNG (BULLISH)"
        sentiment_icon = "🟢"
    elif "BEARISH" in trend_upper:
        trend_display = "🔻 ĐÀ GIẢM (BEARISH)"
        sentiment_icon = "🔴"
    else:
        trend_display = "⚖️ ĐI NGANG (SIDEWAY)"
        sentiment_icon = "🟡"

    # 3. Vẽ thanh Sức mạnh (Sentiment Bar)
    try:
        norm_score = max(0, min(10, int((score + 10) / 2)))
    except:
        norm_score = 5 # Fallback
    
    if norm_score <= 3:
        bar_char = "🟥"
        empty_char = "⬜"
    elif norm_score <= 6:
        bar_char = "🟨"
        empty_char = "⬜"
    else:
        bar_char = "🟩"
        empty_char = "⬜"
        
    progress_bar = (bar_char * norm_score) + (empty_char * (10 - norm_score))

    # 4. Format List tin tức
    if bullets:
        bullets_text = "\n".join([f"📌 {point}" for point in bullets])
    else:
        bullets_text = "Wait for updates..."

    # 5. Thời gian report
    now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    # 6. Ghép nội dung
    message = (
        f"🔥 <b>{headline}</b> 🔥\n"
        f"<i>⏰ Cập nhật: {now_str}</i>\n\n"
        
        f"📊 <b>TÍN HIỆU KỸ THUẬT:</b>\n"
        f"👉 <b>{trend_display}</b>\n"
        f"📈 Score: {score}/10\n"
        f"[{progress_bar}]\n"
        f"━━━━━━━━━━━━\n\n"
        
        f"📰 <b>ĐIỂM TIN CHÍNH:</b>\n"
        f"{bullets_text}\n"
        f"━━━━━━━━━━━━\n\n"
        
        f"🎯 <b>KHUYẾN NGHỊ HÀNH ĐỘNG:</b>\n"
        f"<b>{conclusion}</b>\n\n"
        
        f"🤖 <i>A Finance - Exclusive Signal</i>"
    )
    
    return message

def main():
    logger.info(">>> BẮT ĐẦU QUY TRÌNH TỔNG HỢP (AUTO) <<<")

    try:
        # 1. LẤY TIN
        articles = database.get_unprocessed_articles()
        
        logger.info(f"🔍 Tìm thấy {len(articles)} tin để xử lý...")
        
        # 2. VẼ BIỂU ĐỒ TRƯỚC
        logger.info("🎨 ĐANG VẼ BIỂU ĐỒ...")
        price_chart = charter.draw_price_chart() 
        
        # Gom ảnh vào list để gửi
        image_list = []
        if price_chart and os.path.exists(price_chart): 
            image_list.append(price_chart)

        # 3. GỌI AI PHÂN TÍCH
        logger.info("🤖 ĐANG GỬI DỮ LIỆU SANG AI...")
        
        # OLD: last_report = database.get_latest_report()
        # NEW: Lấy dữ liệu kỹ thuật thực tế để AI phân tích chuẩn hơn
        technical_data = charter.get_technical_analysis()
        logger.info(f"   + Context Kỹ thuật: {technical_data.strip()[:50]}...")

        analysis_result = ai_engine.analyze_market(articles, technical_data)

        if analysis_result:
            logger.info("✅ AI PHÂN TÍCH THÀNH CÔNG!")
            
            # Lưu vào DB
            database.save_report(
                content=analysis_result.get('headline', '') + "...", 
                score=analysis_result.get('sentiment_score', 0),
                trend=analysis_result.get('trend', 'N/A')
            )
            
            # Đánh dấu tin đã đọc
            if articles:
                article_ids = [art['id'] for art in articles]
                database.mark_articles_processed(article_ids)

            # 4. GỬI TELEGRAM
            logger.info("🚀 KÍCH HOẠT TELEGRAM BOT...")
            
            final_message = format_telegram_message(analysis_result)
            telegram_bot.run_sending(final_message, image_list)
            
            logger.info("-" * 50)
            logger.info("🎉 QUY TRÌNH HOÀN TẤT!")
            logger.info("-" * 50)
            
        else:
            logger.warning("❌ AI không trả về kết quả hợp lệ hoặc không có tin mới đủ để phân tích.")

    except Exception as e:
        logger.critical(f"🔥 LỖI FATAL TRONG MAIN FLOW: {e}", exc_info=True)

if __name__ == "__main__":
    main()
