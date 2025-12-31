import json
import os
import datetime
import asyncio
from typing import Dict, Any, List
from app.core import database
from app.services import ai_engine

from app.services import charter
from app.services.market_data_service import get_market_data
from app.services.ta_service import get_technical_analysis
from app.services import telegram_bot
from app.core import config 
from app.utils.helpers import get_random_cta

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
    
    # Lấy câu CTA ngẫu nhiên
    cta_text = get_random_cta()
    
    # Xử lý phần Chiến lược Giao dịch (Strict Format)
    signal = data.get('trade_signal', {})
    raw_order_type = signal.get('order_type', 'WAIT').upper()
    reason = data.get('conclusion', 'Không có lý do cụ thể.')
    
    # 1. Relaxed Order Type Check
    if "BUY" in raw_order_type:
        order_type = "BUY"
    elif "SELL" in raw_order_type:
        order_type = "SELL"
    else:
        order_type = "WAIT"
    
    if order_type in ['BUY', 'SELL']:
        # Format số đẹp (bỏ số 0 vô nghĩa)
        def fmt(val):
            if val is None: return "N/A"
            try:
                # Nếu là string số (VD: "2700") -> float -> format
                # Nếu text thường (VD: "2700-2705") -> giữ nguyên
                f_val = float(val) 
                return f"{f_val:g}"
            except ValueError:
                return str(val)

        # Helper tìm value theo nhiều key
        def get_val(keys):
            for k in keys:
                if k in signal and signal[k] is not None:
                    return signal[k]
            return None

        symbol = "XAU/USD"
        entry = fmt(get_val(['entry_price', 'entry', 'price']))
        sl = fmt(get_val(['sl', 'stop_loss', 'stoploss', 'SL']))
        tp1 = fmt(get_val(['tp1', 'tp', 'take_profit', 'TP1', 'target1']))
        tp2 = fmt(get_val(['tp2', 'TP2', 'target2']))
        
        strategy_text = (
            f"🎯 <b>GỢI Ý GIAO DỊCH</b>\n"
            f"<b>🚀 {order_type} {symbol} {entry}</b>\n"
            f"🛑 <b>SL:</b> {sl}\n"
            f"✅ <b>TP1:</b> {tp1}\n"
            f"✅ <b>TP2:</b> {tp2}\n"
            f"<i>(Khuyến nghị: Quản lý vốn 1-2%)</i>"
        )
    else:
        # Trường hợp WAIT hoặc không có signal
        strategy_text = (
            f"⏳ <b>THỊ TRƯỜNG CHƯA RÕ XU HƯỚNG (WAIT)</b>\n"
            f"📝 <b>Lý do:</b> {reason}"
        )

    message = (
        f"{cta_text}\n\n"
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
        
        f"{strategy_text}\n\n"
    )
    
    # 7. Add Source Hashtags
    if articles:
        hashtags = set()
        for art in articles:
            source = art.get('source', '')
            if source:
                tag = source.lower().replace('rss', '').replace(' ', '').replace('.', '').strip()
                if tag:
                    hashtags.add(f"#{tag}")
        
        if hashtags:
            message += " ".join(sorted(hashtags))
    
    return message

async def main():
    logger.info(">>> BẮT ĐẦU QUY TRÌNH TỔNG HỢP (AUTO - ASYNC) <<<")

    try:
        # 1. LẤY TIN
        articles = await database.get_unprocessed_articles()
        
        if not articles:
            logger.info("🔍 Thông tin đã được phân tích ở phiên trước, bỏ qua phân tích.")
            return

        logger.info(f"🔍 Tìm thấy {len(articles)} tin để xử lý...")
        
        # 2. LẤY DỮ LIỆU THỊ TRƯỜNG (Một lần duy nhất)
        logger.info("📊 ĐANG LẤY DỮ LIỆU THỊ TRƯỜNG...")
        
        # Call Async
        market_df, source = await get_market_data()
        
        if market_df is None or market_df.empty:
            logger.error("❌ Không thể lấy dữ liệu thị trường, quy trình có thể bị ảnh hưởng.")
            technical_data = "Không có dữ liệu kỹ thuật."
        else:
            # Lấy thông tin kỹ thuật (CPU bound func but fast)
            technical_data = get_technical_analysis(market_df)
            logger.info(f"   + Technical Info: {technical_data.replace(chr(10), ' | ')}")

        # 3. GỌI AI PHÂN TÍCH (trước khi vẽ chart)
        logger.info("🤖 ĐANG GỬI DỮ LIỆU SANG AI...")
        
        # Context Memory
        last_report = await database.get_latest_report()
        if last_report:
            logger.info(f"   + Tìm thấy Context phiên trước: {last_report.get('trend')} (Score: {last_report.get('sentiment_score')})")
        else:
            logger.info("   + Không tìm thấy báo cáo cũ (Cold Start).")

        # AI Phân tích (Async)
        analysis_result = await ai_engine.analyze_market(articles, technical_data, last_report)
        
        # 4. VẼ BIỂU ĐỒ (Sau khi AI phân tích xong)
        logger.info("🎨 ĐANG VẼ BIỂU ĐỒ...")
        price_chart = None
        if market_df is not None:
             # Fix: Lấy xu hướng từ AI truyền vào chart
            ai_trend_str = analysis_result.get('trend') if analysis_result else None
            
            # RUN IN THREAD for heavy image processing
            price_chart = await asyncio.to_thread(
                charter.draw_price_chart,
                df=market_df, 
                data_source=source, 
                ai_trend=ai_trend_str
            )
            
        # Gom ảnh vào list để gửi
        image_list = []
        if price_chart and os.path.exists(price_chart): 
            image_list.append(price_chart)

        if analysis_result:
            logger.info("✅ AI PHÂN TÍCH THÀNH CÔNG!")
            
            # Lưu vào DB
            await database.save_report(
                content=analysis_result.get('headline', '') + "...", 
                score=analysis_result.get('sentiment_score', 0),
                trend=analysis_result.get('trend', 'N/A'),
                signal_data=analysis_result.get('trade_signal')
            )
            
            # Bridge -> AutoTrader
            tr_signal = analysis_result.get('trade_signal', {})
            # Logic xử lý Order Type mới
            raw_tr_type = tr_signal.get('order_type', 'WAIT').upper().replace(' ', '_')
            
            if "BUY" in raw_tr_type:
                if "LIMIT" in raw_tr_type: tr_type = "BUY_LIMIT"
                elif "STOP" in raw_tr_type: tr_type = "BUY_STOP"
                else: tr_type = "BUY"
            elif "SELL" in raw_tr_type:
                if "LIMIT" in raw_tr_type: tr_type = "SELL_LIMIT"
                elif "STOP" in raw_tr_type: tr_type = "SELL_STOP"
                else: tr_type = "SELL"
            else:
                tr_type = "WAIT"
                
            if tr_type in ['BUY', 'SELL', 'BUY_LIMIT', 'SELL_LIMIT', 'BUY_STOP', 'SELL_STOP']:
                logger.info(f"🔄 Syncing signal {tr_type} to AutoTrader...")
                
                # Extract AI-generated price levels
                ai_entry = tr_signal.get('entry_price') or tr_signal.get('entry')
                ai_sl = tr_signal.get('sl') or tr_signal.get('stop_loss')
                ai_tp = tr_signal.get('tp1') or tr_signal.get('take_profit')
                
                # Convert to float if string
                try:
                    ai_entry = float(ai_entry) if ai_entry else None
                except (ValueError, TypeError):
                    ai_entry = None
                    
                try:
                    ai_sl = float(ai_sl) if ai_sl else None
                except (ValueError, TypeError):
                    ai_sl = None
                    
                try:
                    ai_tp = float(ai_tp) if ai_tp else None
                except (ValueError, TypeError):
                    ai_tp = None
                
                await database.save_trade_signal(
                    symbol="XAUUSD",
                    signal_type=tr_type,
                    source="AI_REPORT",
                    score=analysis_result.get('sentiment_score', 0),
                    entry=ai_entry,
                    sl=ai_sl,
                    tp=ai_tp
                )
                logger.info(f"   📊 AI Levels - Entry: {ai_entry}, SL: {ai_sl}, TP: {ai_tp}")
            
            # Đánh dấu tin đã đọc
            if articles:
                article_ids = [art['id'] for art in articles]
                await database.mark_articles_processed(article_ids)

            # 4. GỬI TELEGRAM
            logger.info("🚀 KÍCH HOẠT TELEGRAM BOT...")
            
            final_message = format_telegram_message(analysis_result, articles)
            await telegram_bot.send_report_to_telegram(final_message, image_list)
            
            # 5. GỬI WORDPRESS LIVEBLOG (Optional)
            # WordPress Service likely needs to be async or wrapped if it does IO.
            # Assuming it's still sync requests based on user context.
            # Wrap in thread for safety.
            try:
                from app.services.wordpress_service import wordpress_service
                
                if wordpress_service.enabled:
                    logger.info("🌐 ĐANG GỬI LÊN WORDPRESS LIVEBLOG...")
                    
                    def run_wp():
                        # Upload chart image và lấy URL
                        image_url = None
                        if price_chart and os.path.exists(price_chart):
                            media_info = wordpress_service.upload_image(price_chart, f"XAU/USD Chart {datetime.datetime.now().strftime('%Y%m%d_%H%M')}")
                            if media_info:
                                image_url = media_info.get('source_url')
                        
                        # Tạo liveblog entry
                        entry_title = f"⏰ {datetime.datetime.now().strftime('%H:%M')} - {analysis_result.get('headline', 'Phân tích XAU/USD')}"
                        
                        wordpress_service.create_liveblog_entry(
                            title=entry_title,
                            content=final_message,
                            image_url=image_url
                        )
                    
                    await asyncio.to_thread(run_wp)
                    
                else:
                    logger.info("ℹ️ WordPress chưa được cấu hình, bỏ qua bước post WP.")
            except Exception as wp_error:
                logger.error(f"❌ Lỗi khi post WordPress Liveblog (không ảnh hưởng Telegram): {wp_error}")
            
            logger.info("-" * 50)
            logger.info("🎉 QUY TRÌNH HOÀN TẤT!")
            logger.info("-" * 50)
            
        else:
            logger.warning("❌ AI không trả về kết quả hợp lệ hoặc không có tin mới đủ để phân tích.")

    except Exception as e:
        logger.critical(f"🔥 LỖI FATAL TRONG MAIN FLOW: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
