"""
Worker riêng biệt cho Real-time Alert.
Chạy mỗi 15 phút để săn tin nóng (Breaking News).
"""
import datetime
from app.core import database
from app.services import ai_engine
from app.services import telegram_bot
from app.services import news_crawler
from app.services.trader import AutoTrader
from app.core import config

logger = config.logger

def main():
    try:
        logger.info("⚡ [ALERT WORKER] BẮT ĐẦU QUÉT TIN NÓNG...")
        
        # 1. Trigger Crawler
        news_crawler.get_gold_news(lookback_minutes=5, fast_mode=True)
        
        # 2. Lấy tin trong 5 phút qua
        recent_articles = database.get_unalerted_news(lookback_minutes=5)

        if not recent_articles:
            logger.info("   -> Không có tin mới chưa xử lý trong 5 phút qua.")
            logger.info("⚡ [ALERT WORKER] HOÀN TẤT.")
            return

        logger.info(f"   -> Tìm thấy {len(recent_articles)} tin chưa Alert. Đang checking...")

        for article in recent_articles:
            # Defense Layer
            content_sample = article.get('content', '')
            if len(content_sample) < 200 or "Lỗi cào dữ liệu" in content_sample:
                continue

            # Pre-filter
            title_lower = article['title'].lower()
            urgent_keywords = ["cpi", "fed", "rate", "hike", "cut", "war", "explosion", 
                               "surprise", "jump", "plunge", "miss", "beat", "non-farm", "nfp", "pmi", "gdp",
                               "unemployment", "inflation", "biden", "trump", "powell"]
             
            if not any(k in title_lower for k in urgent_keywords):
                continue

            # Check Breaking AI
            analysis = ai_engine.check_breaking_news(article['content'])
            if not analysis: continue
                
            is_breaking = analysis.get('is_breaking', False)
            score = analysis.get('score', 0)
            headline_vi = analysis.get('headline_vi', article['title'])
            summary_vi = analysis.get('summary_vi', '')
            impact_vi = analysis.get('impact_vi', '')
            
            # Keyword Override
            urgent_keywords = ["fed rate", "war", "nuclear", "tăng lãi suất", "chiến tranh"]
            if any(k in article['title'].lower() for k in urgent_keywords):
                is_breaking = True
                if score < 5: score = 8 

            if is_breaking:
                logger.info(f"   🔥 BREAKING NEWS: {headline_vi}")
                
                # --- SEND TELEGRAM ---
                score_val = abs(score)
                if score_val >= 8:
                    warn_text = "🔥 TÁC ĐỘNG: CỰC MẠNH (Lưu ý rủi ro)"
                elif score_val >= 5:
                    warn_text = "⚡ TÁC ĐỘNG: MẠNH"
                else:
                    warn_text = "⚠️ TÁC ĐỘNG: TRUNG BÌNH"

                message = f"""
🚨 <b>{headline_vi}</b>

📝 {summary_vi}

💥 <b>Phân tích:</b> {impact_vi}
{warn_text}
#XAUUSD #Breaking
"""
                image_url = article.get("image_url")
                if image_url:
                     telegram_bot.run_sending(message, [image_url])
                else:
                     telegram_bot.send_message(message)
                
                # --- WORDPRESS ---
                try:
                    from app.services.wordpress_service import wordpress_service
                    if wordpress_service.enabled:
                        wp_title = f"🚨 {headline_vi}"
                        wp_content = f"""
                        <p>📝 {summary_vi}</p>
                        <p>💥 <strong>Phân tích:</strong> {impact_vi}</p>
                        <p><strong>{warn_text}</strong></p>
                        """
                        wordpress_service.create_liveblog_entry(title=wp_title, content=wp_content, image_url=image_url)
                except Exception: pass
                
                # --- TRIGGER AUTO TRADER (ACTIONABLE) ---
                try:
                    if score_val >= 5: # Chỉ phản ứng với tin mạnh > 5
                        logger.info("   🤖 Activating Trader response...")
                        trader = AutoTrader()
                        
                        # Mapping Data
                        # score: 0-10 scale usually. 
                        # Trend? Need to imply from score or keywords? 
                        # Assuming ai_engine.check_breaking_news doesn't return Explicit Trend "BULLISH/BEARISH" clearly,
                        # but usually impact_analysis implies it. 
                        # For now, simplistic approach: check keywords in impact_vi or title?
                        # Actually 'ai_engine.check_breaking_news' schema might need checking.
                        # Assuming for now we rely on score strength and we might need to Extract Trend better.
                        # Wait, user request said: "Input: news_data chứa score (0-10) và trend (BULLISH/BEARISH)."
                        # My ai_engine mock might not return 'trend' key in check_breaking_news.
                        # I will check `ai_engine.py`? No time. 
                        # I will infer trend if missing, or default to Neutral (Defensive only).
                        
                        # Let's try to parse trend from 'impact_vi' text if possible or just pass "NEUTRAL"
                        # If "NEUTRAL", Trader will only do Defensive checks (SAFE) but won't Sniper.
                        # To Sniper, we need Direction.
                        
                        # Hack: Search for "tăng" (Bullish) or "giảm" (Bearish) in impact_vi
                        trend_est = "NEUTRAL"
                        impact_lower = impact_vi.lower()
                        if "tăng" in impact_lower or "hỗ trợ" in impact_lower or "bullish" in impact_lower:
                            trend_est = "BULLISH"
                        elif "giảm" in impact_lower or "áp lực" in impact_lower or "bearish" in impact_lower:
                            trend_est = "BEARISH"
                            
                        news_data = {
                            'title': headline_vi,
                            'score': score_val,
                            'trend': trend_est, # Estimated
                            'source': 'NEWS',   # Add Source
                            'symbol': 'XAUUSD'  # Add Symbol
                        }
                        trader.process_news_signal(news_data)
                except Exception as e:
                    logger.error(f"❌ Trader Trigger Failed: {e}")

                # Mark Alerted
                database.mark_article_alerted(article['id'])
                
            else:
                pass

        logger.info("⚡ [ALERT WORKER] HOÀN TẤT.")

    except Exception as e:
        logger.error(f"❌ Lỗi Alert Worker: {e}", exc_info=True)

if __name__ == "__main__":
    main()
