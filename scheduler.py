"""
Scheduler - Tự động quét tin và phân tích mỗi giờ

Script này sẽ:
- Quét tin từ RSS mỗi 1 tiếng
- Phân tích và gửi telegram khi có tin mới
- Chạy liên tục 24/7
"""

import schedule
import time
import database
import run_analysis
import config
from datetime import datetime

logger = config.logger

def job_scan_news():
    """Job quét tin từ RSS"""
    try:
        logger.info("="*60)
        logger.info(f"🕐 [{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] BẮT ĐẦU QUÉT TIN...")
        logger.info("="*60)
        
        # Quét tin từ RSS
        database.get_gold_news()
        
        logger.info("✅ Quét tin hoàn tất!")
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi quét tin: {e}", exc_info=True)

def job_analyze_and_send():
    """Job phân tích và gửi telegram"""
    try:
        logger.info("="*60)
        logger.info(f"📊 [{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] BẮT ĐẦU PHÂN TÍCH...")
        logger.info("="*60)
        
        # Chạy phân tích và gửi telegram
        run_analysis.main()
        
        logger.info("✅ Phân tích và gửi hoàn tất!")
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi phân tích: {e}", exc_info=True)

def main():
    """Hàm chính - Thiết lập và chạy scheduler"""
    logger.info("🚀 KHỞI ĐỘNG SCHEDULER...")
    logger.info("📅 Lịch trình:")
    logger.info("   - Quét tin: Mỗi 1 giờ")
    logger.info("   - Phân tích: 5 phút sau mỗi lần quét")
    logger.info("="*60)
    
    # Thiết lập lịch trình
    # Quét tin mỗi giờ
    schedule.every(1).hours.do(job_scan_news)
    
    # Phân tích và gửi telegram 5 phút sau mỗi lần quét
    schedule.every(1).hours.at(":05").do(job_analyze_and_send)
    
    # Chạy ngay lần đầu tiên
    logger.info("🔄 Chạy lần đầu tiên...")
    job_scan_news()
    time.sleep(60)  # Đợi 1 phút
    job_analyze_and_send()
    
    # Vòng lặp chính
    logger.info("♾️  Bắt đầu vòng lặp tự động...")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check mỗi phút
    except KeyboardInterrupt:
        logger.info("\n⏹️  Dừng scheduler bởi người dùng")
    except Exception as e:
        logger.critical(f"🔥 LỖI NGHIÊM TRỌNG: {e}", exc_info=True)

if __name__ == "__main__":
    main()
