"""
Worker riêng biệt cho Real-time Alert.
Chạy mỗi 15 phút để săn tin nóng (Breaking News).
"""
import datetime
from app.core import database
from app.services import ai_engine
from app.services import telegram_bot
from app.services import news_crawler
from app.core import config
from app.core import config

logger = config.logger

def main():
    try:
        logger.info("⚡ [ALERT WORKER] BẮT ĐẦU QUÉT TIN NÓNG...")
        
        # 1. Trigger Crawler để đảm bảo DB có tin mới nhất
        # Crawler sẽ tự động lưu tin mới vào DB (nếu có)
        # Crawler sẽ tự động lưu tin mới vào DB (nếu có)
        # Chúng ta KHÔNG dùng giá trị trả về của crawler nữa, mà query DB
        # để đảm bảo cả những tin vừa scan ở bước khác cũng được tính.
        # 2. Crawler update
        # Sử dụng fast_mode=True và lookback ngắn (5 phút) cho HFT
        news_crawler.get_gold_news(lookback_minutes=6000, fast_mode=True)
        
        # 3. Lấy tin trong 5 phút qua
        recent_articles = database.get_unalerted_news(lookback_minutes=6000)

        if not recent_articles:
            logger.info("   -> Không có tin mới chưa xử lý trong 20 phút qua.")
            logger.info("⚡ [ALERT WORKER] HOÀN TẤT.")
            return

        logger.info(f"   -> Tìm thấy {len(recent_articles)} tin chưa Alert. Đang checking...")

        for article in recent_articles:
            # 2. Pre-filter: Chỉ check AI nếu tiêu đề chứa từ khóa mạnh (Tiết kiệm Token & Tăng tốc)
            title_lower = article['title'].lower()
            urgent_keywords = ["cpi", "fed", "rate", "hike", "cut", "war", "explosion", 
                               "surprise", "jump", "plunge", "miss", "beat", "non-farm", "nfp", "pmi", "gdp",
                               "unemployment", "inflation", "biden", "trump", "powell"]
             
            if not any(k in title_lower for k in urgent_keywords):
                logger.info(f"   -> Skip (Low Impact Title): {article['title']}")
                continue

            # 3. Check Breaking bằng AI
            analysis = ai_engine.check_breaking_news(article['content'])
            
            if not analysis:
                continue
                
            is_breaking = analysis.get('is_breaking', False)
            score = analysis.get('score', 0)
            headline_vi = analysis.get('headline_vi', article['title'])
            summary_vi = analysis.get('summary_vi', '')
            impact_vi = analysis.get('impact_vi', '')
            
            # Logic override: Nếu tiêu đề chứa từ khóa cực mạnh, force Breaking luôn
            urgent_keywords = ["fed rate", "war", "nuclear", "tăng lãi suất", "chiến tranh"]
            if any(k in article['title'].lower() for k in urgent_keywords):
                is_breaking = True
                if score == 0: score = -5 

            if is_breaking:
                logger.info(f"   🔥 BREAKING NEWS: {headline_vi}")
                
                # 3. Gửi ngay Telegram
                trend_icon = "🟢" if score > 0 else "🔴" if score < 0 else "🟡"
                trend_text = "BULLISH" if score > 0 else "BEARISH" if score < 0 else "NEUTRAL"

                message = f"""
🚨 <b>{headline_vi}</b>

📝 {summary_vi}

💥 <b>Tác động:</b> {impact_vi}
{trend_icon} <b>Xu hướng:</b> {trend_text}
#XAUUSD #Breaking
"""
                # Check Image
                image_url = article.get("image_url")
                if image_url:
                     telegram_bot.run_sending(message, [image_url])
                else:
                     telegram_bot.send_message(message)
                
                # 4. Gửi WordPress Liveblog
                try:
                    from app.services.wordpress_service import wordpress_service
                    
                    if wordpress_service.enabled:
                        logger.info("🌐 Đang gửi Breaking News lên WordPress...")
                        
                        # Tiêu đề entry
                        wp_title = f"🚨 {headline_vi}"
                        
                        # Nội dung HTML (Construct manual HTML to be safe)
                        wp_content = f"""
                        <p>📝 {summary_vi}</p>
                        <p>💥 <strong>Tác động:</strong> {impact_vi}</p>
                        <p>{trend_icon} <strong>Xu hướng:</strong> {trend_text}</p>
                        """
                        
                        wordpress_service.create_liveblog_entry(
                            title=wp_title,
                            content=wp_content, 
                            image_url=image_url
                        )
                except Exception as e:
                    logger.error(f"❌ Lỗi gửi WP: {e}")
                
                # 4. Đánh dấu đã Alert
                database.mark_article_alerted(article['id'])
                
            else:
                logger.info(f"   -> Tin thường (Skip): {article['title']} (Score: {score})")
                
                # OPTIONAL: Nếu tin quá nhạt, có thể mark alerted luôn để lần sau k check lại?
                # Nhưng logic hiện tại chỉ lấy tin trong 20p, nên sau 20p nó tự trôi.
                # Tuy nhiên, để tiết kiệm tiền AI, ta có thể mark luôn là 0 (đã check) nhưng k gửi?
                # Hiện tại giữ nguyên (check lại mỗi lần cũng được, vì window ngắn 20p)
                pass

        logger.info("⚡ [ALERT WORKER] HOÀN TẤT.")

    except Exception as e:
        logger.error(f"❌ Lỗi Alert Worker: {e}", exc_info=True)

if __name__ == "__main__":
    main()
