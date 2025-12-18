"""
Worker riêng biệt cho Real-time Alert (Async).
"""
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
        logger.info("⚡ [ALERT WORKER] BẮT ĐẦU QUÉT TIN NÓNG...")
        
        # 1. Trigger Crawler (Async)
        await news_crawler.get_gold_news(lookback_minutes=5, fast_mode=True)
        
        # 2. Lấy tin trong 5 phút qua
        recent_articles = await database.get_unalerted_news(lookback_minutes=5)

        if not recent_articles:
            logger.info("   -> Không có tin mới chưa xử lý trong 5 phút qua.")
            logger.info("⚡ [ALERT WORKER] HOÀN TẤT.")
            return

        logger.info(f"   -> Tìm thấy {len(recent_articles)} tin chưa Alert. Đang checking...")

        # Định nghĩa từ khóa lọc (chuyển ra ngoài vòng lặp để tối ưu)
        URGENT_KEYWORDS = [
            "cpi", "fed", "rate", "hike", "cut", "war", "explosion", 
            "surprise", "jump", "plunge", "miss", "beat", "non-farm", "nfp", 
            "pmi", "gdp", "unemployment", "inflation", "biden", "trump", "powell"
        ]
        
        OVERRIDE_KEYWORDS = ["fed rate", "war", "nuclear", "tăng lãi suất", "chiến tranh"]

        for article in recent_articles:
            try:
                # --- 1. Defense Layer ---
                content_sample = article.get('content', '')
                if len(content_sample) < 200 or "Lỗi cào dữ liệu" in content_sample:
                    continue

                # --- 2. Pre-filter Keywords ---
                title_lower = article['title'].lower()
                
                if not any(k in title_lower for k in URGENT_KEYWORDS):
                    logger.info(f"   -> Skip tin: {article['title']} (Không có keyword khẩn cấp)")
                    continue

                # --- 3. Check Breaking AI (Async) ---
                analysis = await ai_engine.check_breaking_news(article['content'])
                if not analysis: continue
                    
                is_breaking = analysis.get('is_breaking', False)
                score = analysis.get('score', 0)
                headline_vi = analysis.get('headline_vi', article['title'])
                summary_vi = analysis.get('summary_vi', '')
                impact_vi = analysis.get('impact_vi', '')
                
                # Keyword Override (Luôn báo nếu có từ khóa cực nóng)
                if any(k in title_lower for k in OVERRIDE_KEYWORDS):
                    is_breaking = True
                    if score < 5: score = 8 

                if is_breaking:
                    logger.info(f"   🔥 BREAKING NEWS: {headline_vi}")
                    
                    # --- SEND TELEGRAM ---
                    score_val = abs(score)
                    if score_val >= 8:
                        warn_text = "🔥 <b>TÁC ĐỘNG: CỰC MẠNH</b>"
                    elif score_val >= 5:
                        warn_text = "⚡ <b>TÁC ĐỘNG: MẠNH</b>"
                    else:
                        warn_text = "⚠️ <b>TÁC ĐỘNG: TRUNG BÌNH</b>"

                    # Format Message Gọn Gàng
                    message = (
                        f"🚨 <b>{headline_vi}</b>\n\n"
                        f"📝 {summary_vi}\n"
                        f"💥 <b>Phân tích:</b> {impact_vi}\n"
                        f"{warn_text} #Breaking"
                    )

                    image_url = article.get("image_url")
                    if image_url:
                         await telegram_bot.send_report_to_telegram(message, [image_url])
                    else:
                         await telegram_bot.send_message_async(message)
                    
                    # --- WORDPRESS (Optional) ---
                    try:
                        from app.services.wordpress_service import wordpress_service
                        if wordpress_service.enabled:
                            wp_title = f"🚨 {headline_vi}"
                            wp_content = f"""
                            <p>📝 {summary_vi}</p>
                            <p>💥 <strong>Phân tích:</strong> {impact_vi}</p>
                            <p><strong>{warn_text}</strong></p>
                            """
                            # Chạy sync trong thread riêng
                            await asyncio.to_thread(
                                wordpress_service.create_liveblog_entry, 
                                title=wp_title, content=wp_content, image_url=image_url
                            )
                    except Exception as e: 
                        logger.error(f"❌ Failed to create WordPress entry: {e}")
                    
                    # --- TRIGGER AUTO TRADER ---
                    try:
                        if score_val >= 5: 
                            logger.info("   🤖 Activating Trader response...")
                            trader = AutoTrader()
                            
                            trend_est = "NEUTRAL"
                            impact_lower = impact_vi.lower()
                            if "tăng" in impact_lower or "hỗ trợ" in impact_lower or "bullish" in impact_lower:
                                trend_est = "BULLISH"
                            elif "giảm" in impact_lower or "áp lực" in impact_lower or "bearish" in impact_lower:
                                trend_est = "BEARISH"
                                
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

            except Exception as e:
                logger.error(f"❌ Error processing article {article.get('id')}: {e}")
            
            finally:
                # QUAN TRỌNG: Luôn đánh dấu đã check để không quét lại lần sau (tránh loop)
                await database.mark_article_alerted(article['id'])

        logger.info("⚡ [ALERT WORKER] HOÀN TẤT.")

    except Exception as e:
        logger.error(f"❌ Lỗi Alert Worker: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())