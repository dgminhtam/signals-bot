"""
Scheduler - Tự động quét tin và phân tích theo 3 khung giờ chiến lược

Script này sẽ:
- Quét tin và phân tích vào 3 khung giờ: 07:00, 13:30, 19:00
- Chỉ chạy từ Thứ 2 đến Thứ 6 (thị trường Forex/Gold nghỉ cuối tuần)
- Gửi báo cáo qua Telegram
"""

import schedule
import time
from datetime import datetime
from app.core import config
from app.services import news_crawler
from app.jobs import daily_report
from app.jobs import realtime_alert

logger = config.logger

def is_weekday():
    """Kiểm tra có phải ngày làm việc không (Thứ 2-6)
    
    Returns:
        bool: True nếu là Thứ 2-6, False nếu là Thứ 7-CN
        Monday=0, Tuesday=1, ..., Friday=4, Saturday=5, Sunday=6
    """
    return datetime.now().weekday() < 5  # 0-4 là Thứ 2-6

def job_scan_news():
    """Job quét tin từ RSS"""
    # Kiểm tra cuối tuần
    if not is_weekday():
        logger.info("🏖️ Cuối tuần (Thứ 7/CN) - Thị trường Forex/Gold nghỉ, bot nghỉ!")
        return
    
    try:
        logger.info("="*60)
        logger.info(f"🕐 [{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] BẮT ĐẦU QUÉT TIN...")
        logger.info("="*60)
        
        # Quét tin từ RSS
        news_crawler.get_gold_news()
        
        logger.info("✅ Quét tin hoàn tất!")
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi quét tin: {e}", exc_info=True)

def job_analyze_and_send():
    """Job phân tích và gửi telegram"""
    # Kiểm tra cuối tuần
    if not is_weekday():
        logger.info("🏖️ Cuối tuần (Thứ 7/CN) - Thị trường Forex/Gold nghỉ, bot nghỉ!")
        return
    
    try:
        logger.info("="*60)
        logger.info(f"📊 [{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] BẮT ĐẦU PHÂN TÍCH...")
        logger.info("="*60)
        
        # Chạy phân tích và gửi telegram
        daily_report.main()
        
        logger.info("✅ Phân tích và gửi hoàn tất!")
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi phân tích: {e}", exc_info=True)

def main():
    """Hàm chính - Thiết lập và chạy scheduler"""
    logger.info("🚀 KHỞI ĐỘNG SCHEDULER (Clean Architecture Version)...")
    logger.info("📅 Lịch trình: 3 Khung giờ Chiến lược (Thứ 2-6)")
    logger.info("🏖️ Bot nghỉ: Thứ 7, Chủ Nhật (Thị trường Forex/Gold đóng cửa)")
    logger.info("="*60)
    logger.info("🕐 KHUNG GIỜ 1: Báo cáo Đầu ngày (Phiên Á)")
    logger.info("   ⏰ 07:00 - Quét tin")
    logger.info("   📊 07:15 - Phân tích và gửi")
    logger.info("   💡 Lý do: Daily candle đóng, phiên Á bắt đầu")
    logger.info("-"*60)
    logger.info("🕐 KHUNG GIỜ 2: Chuẩn bị Phiên Âu (London Open)")
    logger.info("   ⏰ 13:30 - Quét tin")
    logger.info("   📊 13:45 - Phân tích và gửi")
    logger.info("   💡 Lý do: Trước London mở cửa, thanh khoản tăng mạnh")
    logger.info("-"*60)
    logger.info("🕐 KHUNG GIỜ 3: Trước Phiên Mỹ (New York Open) 🔥 QUAN TRỌNG")
    logger.info("   ⏰ 19:00 - Quét tin")
    logger.info("   📊 19:15 - Phân tích và gửi")
    logger.info("   💡 Lý do: Giờ vàng XAU/USD, 80% biến động mạnh")
    logger.info("="*60)
    
    # Thiết lập lịch trình - 3 khung giờ
    # KHUNG GIỜ 1: Phiên Á (07:00 - 07:30)
    schedule.every().day.at("07:00").do(job_scan_news)
    schedule.every().day.at("07:15").do(job_analyze_and_send)
    
    # KHUNG GIỜ 2: Phiên Âu (13:30 - 14:00)
    schedule.every().day.at("13:30").do(job_scan_news)
    schedule.every().day.at("13:45").do(job_analyze_and_send)
    
    # KHUNG GIỜ 3: Phiên Mỹ (19:00 - 19:30) - QUAN TRỌNG NHẤT
    schedule.every().day.at("19:00").do(job_scan_news)
    schedule.every().day.at("19:15").do(job_analyze_and_send)
    
    # --- NEW: REAL-TIME ALERT (Chạy mỗi 15 phút) ---
    logger.info("⚡ Thiết lập Real-time Alert: Chạy mỗi 15 phút (Chỉ quét tin mới & cực nóng)")
    schedule.every(15).minutes.do(realtime_alert.main)
    
    logger.info(f"✅ Đã thiết lập jobs: 3 khung giờ chính + Alert 15p/lần")
    logger.info("")

    
    # Chạy ngay lần đầu tiên để test
    logger.info("🔄 Chạy test lần đầu tiên...")
    # job_scan_news()
    # time.sleep(10)  # Đợi 10 giây
    # job_analyze_and_send()
    
    # Vòng lặp chính
    logger.info("♾️  Bắt đầu vòng lặp tự động...")
    logger.info("⏰ Chờ đến các khung giờ: 07:00, 13:30, 19:00...")
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
