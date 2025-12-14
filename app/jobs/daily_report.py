import json
import os
import datetime
from typing import Dict, Any, List
from app.core import database
from app.services import ai_engine
from app.services import charter
from app.services import telegram_bot
from app.core import config 

logger = config.logger

def format_telegram_message(data: Dict[str, Any], articles: List[Dict[str, Any]] = None) -> str:
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

    # # 3. Vẽ thanh Sức mạnh (Sentiment Bar)
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
        f"<b>{trend_display}</b>\n"
        f"<b>📈 Score: {score}/10</b>\n"
        f"{progress_bar}\n"
        f"━━━━━━━━━━━━\n\n"
        
        f"📰 <b>ĐIỂM TIN CHÍNH:</b>\n"
        f"{bullets_text}\n"
        f"━━━━━━━━━━━━\n\n"
        
        f"🎯 <b>GỢI Ý GIAO DỊCH</b>\n"
        f"{conclusion}\n\n"
    )
    
    # 7. Add Source Hashtags
    if articles:
        hashtags = set()
        for art in articles:
            source = art.get('source', '')
            if source:
                # Cleanup: "RSS CNN Money" -> "#cnnmoney", "Kitco News" -> "#kitconews"
                tag = source.lower().replace('rss', '').replace(' ', '').replace('.', '').strip()
                if tag:
                    hashtags.add(f"#{tag}")
        
        if hashtags:
            message += " ".join(sorted(hashtags))
    
    return message

def main():
    logger.info(">>> BẮT ĐẦU QUY TRÌNH TỔNG HỢP (AUTO) <<<")

    try:
        # 1. LẤY TIN
        articles = database.get_unprocessed_articles()
        
        logger.info(f"🔍 Tìm thấy {len(articles)} tin để xử lý...")
        
        # 2. LẤY DỮ LIỆU THỊ TRƯỜNG (Một lần duy nhất)
        logger.info("📊 ĐANG LẤY DỮ LIỆU THỊ TRƯỜNG...")
        market_df, source = charter.get_market_data()
        
        if market_df is None or market_df.empty:
            logger.error("❌ Không thể lấy dữ liệu thị trường, quy trình có thể bị ảnh hưởng.")
            technical_data = "Không có dữ liệu kỹ thuật."
        else:
            # Lấy thông tin kỹ thuật (Price, Support, Resistance)
            technical_data = charter.get_technical_analysis(market_df)
            logger.info(f"   + Technical Info: {technical_data.replace(chr(10), ' | ')}")

        # 3. GỌI AI PHÂN TÍCH (trước khi vẽ chart)
        logger.info("🤖 ĐANG GỬI DỮ LIỆU SANG AI...")
        
        # Context Memory: Lấy báo cáo phiên trước để AI so sánh
        last_report = database.get_latest_report()
        if last_report:
            logger.info(f"   + Tìm thấy Context phiên trước: {last_report.get('trend')} (Score: {last_report.get('sentiment_score')})")
        else:
            logger.info("   + Không tìm thấy báo cáo cũ (Cold Start).")

        # AI Phân tích
        analysis_result = ai_engine.analyze_market(articles, technical_data, last_report)
        
        # 4. VẼ BIỂU ĐỒ (Sau khi AI phân tích xong)
        logger.info("🎨 ĐANG VẼ BIỂU ĐỒ...")
        price_chart = None
        if market_df is not None:
            price_chart = charter.draw_price_chart(df=market_df, data_source=source)
            
        # Gom ảnh vào list để gửi
        image_list = []
        if price_chart and os.path.exists(price_chart): 
            image_list.append(price_chart)

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
            
            final_message = format_telegram_message(analysis_result, articles)
            telegram_bot.run_sending(final_message, image_list)
            
            # 5. GỬI WORDPRESS LIVEBLOG (Optional - không ảnh hưởng Telegram)
            try:
                from app.services.wordpress_service import wordpress_service
                
                if wordpress_service.enabled:
                    logger.info("🌐 ĐANG GỬI LÊN WORDPRESS LIVEBLOG...")
                    
                    # Upload chart image và lấy URL
                    image_url = None
                    if price_chart and os.path.exists(price_chart):
                        media_info = wordpress_service.upload_image(price_chart, f"XAU/USD Chart {datetime.datetime.now().strftime('%Y%m%d_%H%M')}")
                        if media_info:
                            # Lấy URL trực tiếp từ response của WordPress
                            image_url = media_info.get('source_url')
                    
                    # Tạo liveblog entry
                    entry_title = f"⏰ {datetime.datetime.now().strftime('%H:%M')} - {analysis_result.get('headline', 'Phân tích XAU/USD')}"
                    
                    wordpress_service.create_liveblog_entry(
                        title=entry_title,
                        content=final_message,
                        image_url=image_url
                    )
                else:
                    logger.info("ℹ️ WordPress chưa được cấu hình, bỏ qua bước post WP.")
            except Exception as wp_error:
                # Lỗi WordPress KHÔNG được phép làm crash Telegram flow
                logger.error(f"❌ Lỗi khi post WordPress Liveblog (không ảnh hưởng Telegram): {wp_error}")
            
            logger.info("-" * 50)
            logger.info("🎉 QUY TRÌNH HOÀN TẤT!")
            logger.info("-" * 50)
            
        else:
            logger.warning("❌ AI không trả về kết quả hợp lệ hoặc không có tin mới đủ để phân tích.")

    except Exception as e:
        logger.critical(f"🔥 LỖI FATAL TRONG MAIN FLOW: {e}", exc_info=True)

if __name__ == "__main__":
    main()
