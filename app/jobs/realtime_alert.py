"""
Worker riêng biệt cho Real-time Alert (Async).
"""
import datetime
import asyncio
from app.core import database
from app.services import ai_engine
from app.services import telegram_bot
from app.services import news_crawler
from app.services.trader import AutoTrader
from app.core import config

logger = config.logger

async def main():
    try:
        logger.debug("⚡ [ALERT WORKER] BẮT ĐẦU QUÉT TIN NÓNG...")
        
        # 1. Trigger Crawler (Async)
        # Note: get_gold_news should be awaited
        await news_crawler.get_gold_news(lookback_minutes=5, fast_mode=True)
        
        # 2. Lấy tin trong 5 phút qua
        recent_articles = await database.get_unalerted_news(lookback_minutes=5)

        if not recent_articles:
            logger.debug("   -> Không có tin mới chưa xử lý trong 5 phút qua.")
            return

        logger.debug(f"   -> Tìm thấy {len(recent_articles)} tin chưa Alert. Đang checking...")

        for article in recent_articles:
            # Defense Layer
            content_sample = article.get('content', '')
            if len(content_sample) < 200 or "Lỗi cào dữ liệu" in content_sample:
                continue

            # Pre-filter
            title_lower = article['title'].lower()

            # --- BLACKLIST FILTER: Loại bỏ tin không liên quan ---
            ignore_keywords = ["eur", "gbp", "jpy", "aud", "nzd", "cad", "ecb", "boe", "boj", "rba", "oil", "crypto", "btc", "eth"]
            if any(k in title_lower for k in ignore_keywords):
                logger.debug(f"   -> SKIP: Tin chứa từ khóa ngoại lai ({article['title']})")
                continue
            # ---------------------------------------------------

            urgent_keywords = ["cpi", "fed", "rate", "hike", "cut", "war", "explosion", 
                               "surprise", "jump", "plunge", "miss", "beat", "non-farm", "nfp", "pmi", "gdp",
                               "unemployment", "inflation", "biden", "trump", "powell"]
             
            if not any(k in title_lower for k in urgent_keywords):
                continue

            # Check Breaking AI (Async)
            analysis = await ai_engine.check_breaking_news(article['content'])
            if not analysis: continue
                
            is_breaking = analysis.get('is_breaking', False)
            score = analysis.get('score', 0)
            headline_vi = analysis.get('headline_vi', article['title'])
            summary_vi = analysis.get('summary_vi', '')
            impact_vi = analysis.get('impact_vi', '')
            
            # Keyword Override
            urgent_keywords_vi = ["fed rate", "war", "nuclear", "tăng lãi suất", "chiến tranh"]
            if any(k in article['title'].lower() for k in urgent_keywords_vi):
                is_breaking = True
                if score < 5: score = 8 

            if is_breaking:
                logger.warning(f"🔥 BREAKING NEWS: {headline_vi}")
                
                # --- SEND TELEGRAM ---
                score_val = abs(score)
                if score_val >= 8:
                    warn_text = "🔥 TÁC ĐỘNG: CỰC MẠNH (Lưu ý rủi ro)"
                elif score_val >= 5:
                    warn_text = "⚡ TÁC ĐỘNG: MẠNH"
                else:
                    warn_text = "⚠️ TÁC ĐỘNG: TRUNG BÌNH"

                message = (
                        f"🚨 <b>{headline_vi}</b>\n\n"
                        f"📝 {summary_vi}\n"
                        f"💥 <b>Phân tích:</b> {impact_vi}\n"
                        f"{warn_text} \n"
                        f"#Breaking"
                    )
                image_url = article.get("image_url")
                if image_url:
                     await telegram_bot.send_report_to_telegram(message, [image_url])
                     logger.info("✅ Đã gửi Breaking News đến Telegram (có ảnh)")
                else:
                     await telegram_bot.send_message_async(message)
                     logger.info("✅ Đã gửi Breaking News đến Telegram")
                
                # --- WORDPRESS (Sync wrapped in Thread) ---
                try:
                    from app.services.wordpress_service import wordpress_service
                    if wordpress_service.enabled:
                        wp_title = f"🚨 {headline_vi}"
                        wp_content = (
                            f"📝 {summary_vi}\n"
                            f"💥 <strong>Phân tích:</strong> {impact_vi}\n"
                            f"<strong>{warn_text}</strong>"
                        )
                        # Assuming create_liveblog_entry is sync
                        await asyncio.to_thread(
                            wordpress_service.create_liveblog_entry, 
                            title=wp_title, content=wp_content, image_url=image_url
                        )
                except Exception as e: 
                    logger.error(f"❌ WordPress Error: {e}")
                
                # --- TRIGGER AUTO TRADER (ACTIONABLE) ---
                try:
                    if score_val >= 5: 
                        logger.info("🤖 Activating Auto Trader...")
                        trader = AutoTrader()
                        ai_trend = analysis.get('trend_forecast', 'NEUTRAL').upper()
                        if ai_trend == "BULLISH":
                            trend_est = "BULLISH"
                            logger.info("   📈 AI Prediction: Vàng sẽ TĂNG giá.")
                        elif ai_trend == "BEARISH":
                            trend_est = "BEARISH"
                            logger.info("   📉 AI Prediction: Vàng sẽ GIẢM giá.")
                        else:
                            trend_est = "NEUTRAL"
                            logger.info("   ⚖️ AI Prediction: Không rõ xu hướng hoặc Sideway.")
                            
                        news_data = {
                            'title': headline_vi,
                            'score': score_val,
                            'trend': trend_est, 
                            'source': 'NEWS', 
                            'symbol': 'XAUUSD'
                        }
                        await trader.process_news_signal(news_data)
                except Exception as e:
                    logger.error(f"❌ Trader Trigger Failed: {e}")

                # Mark Alerted
                await database.mark_article_alerted(article['id'])
                
            else:
                pass

    except Exception as e:
        logger.error(f"❌ Lỗi Alert Worker: {e}", exc_info=True)

    finally:
        logger.debug("⚡ [ALERT WORKER] HOÀN TẤT.")

if __name__ == "__main__":
    asyncio.run(main())