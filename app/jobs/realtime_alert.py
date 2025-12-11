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

logger = config.logger

def main():
    try:
        logger.info("⚡ [ALERT WORKER] BẮT ĐẦU QUÉT TIN NÓNG...")
        
        # 1. Quét tin trong 20 phút gần nhất (Gối đầu 5 phút cho chắc)
        # Scheduler chạy 15p/lần -> Quét 20p là hợp lý
        # Uses news_crawler service now
        recent_articles = news_crawler.get_gold_news(lookback_minutes=20)
        
        if not recent_articles:
            logger.info("   -> Không có tin mới trong 20 phút qua.")
            return

        logger.info(f"   -> Tìm thấy {len(recent_articles)} tin mới. Đang kiểm tra độ Hot...")

        for article in recent_articles:
            # 2. Check Breaking bằng AI
            analysis = ai_engine.check_breaking_news(article['content'])
            
            if not analysis:
                continue
                
            is_breaking = analysis.get('is_breaking', False)
            score = analysis.get('score', 0)
            headline = analysis.get('headline', 'Breaking News')
            
            # Logic override: Nếu tiêu đề chứa từ khóa cực mạnh, force Breaking luôn
            # (Phòng trường hợp AI lúc đó ngáo, hoặc muốn bypass logic AI)
            urgent_keywords = ["fed rate", "war", "nuclear", "tăng lãi suất", "chiến tranh"]
            if any(k in article['title'].lower() for k in urgent_keywords):
                is_breaking = True
                if score == 0: score = -5 # Điểm tạm

            if is_breaking:
                logger.info(f"   🔥 BREAKING NEWS PHÁT HIỆN: {article['title']}")
                
                # 3. Gửi ngay Telegram
                # Xác định icon Sentiment
                trend_icon = "🟢" if score > 0 else "🔴" if score < 0 else "🟡"
                trend_text = "BULLISH" if score > 0 else "BEARISH" if score < 0 else "NEUTRAL"
                
                message = f"""
🚨 <b>BREAKING NEWS</b> 🚨

{headline}

{trend_icon} <b>Tác động:</b> {trend_text} (Score: {score})
⏱ <b>Time:</b> {datetime.datetime.now().strftime('%H:%M')}

📝 <b>Nội dung chính:</b>
{article['title']}

<i>AI Quick Alert - Dữ liệu thô chưa qua kiểm chứng kỹ lưỡng.</i>
#Breaking #XAUUSD
"""
                telegram_bot.send_message(message)
                
                # 4. Đánh dấu đã Alert để Daily Report biết (nhưng vẫn giữ status NEW)
                database.mark_article_alerted(article['id'])
                
            else:
                logger.info(f"   -> Tin thường: {article['title']} (Score: {score})")

        logger.info("⚡ [ALERT WORKER] HOÀN TẤT.")

    except Exception as e:
        logger.error(f"❌ Lỗi Alert Worker: {e}", exc_info=True)

if __name__ == "__main__":
    main()
