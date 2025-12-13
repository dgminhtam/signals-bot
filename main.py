"""
Scheduler - Tự động quét tin và phân tích theo 3 khung giờ chiến lược

Script này sẽ:
- Quét tin và phân tích vào 3 khung giờ: 07:00, 13:30, 19:00
- Chỉ chạy từ Thứ 2 đến Thứ 6 (thị trường Forex/Gold nghỉ cuối tuần)
- Gửi báo cáo qua Telegram
"""

import schedule
import time
import argparse
import sys
from datetime import datetime
from app.core import config
from app.services import news_crawler
from app.jobs import daily_report
from app.jobs import realtime_alert
from app.jobs import economic_worker
from app.core import config

logger = config.logger

def is_weekday():
    """Kiểm tra có phải ngày làm việc không (Thứ 2-6)"""
    return datetime.now().weekday() < 5  # 0-4 là Thứ 2-6

def job_scan_news(force=False):
    """Job quét tin từ RSS"""
    # Kiểm tra cuối tuần (nếu không force)
    if not force and not is_weekday():
        logger.info("🏖️ Cuối tuần (Thứ 7/CN) - Thị trường Forex/Gold nghỉ, bot nghỉ!")
        return
    
    try:
        logger.info("="*60)
        mode_str = "MANUAL" if force else "AUTO"
        logger.info(f"🕐 [{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] BẮT ĐẦU QUÉT TIN ({mode_str})...")
        logger.info("="*60)
        
        # Quét tin từ RSS
        news_crawler.get_gold_news()
        
        logger.info("✅ Quét tin hoàn tất!")
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi quét tin: {e}", exc_info=True)

def job_analyze_and_send(force=False):
    """Job phân tích và gửi telegram"""
    # Kiểm tra cuối tuần (nếu không force)
    if not force and not is_weekday():
        logger.info("🏖️ Cuối tuần (Thứ 7/CN) - Thị trường Forex/Gold nghỉ, bot nghỉ!")
        return
    
    try:
        logger.info("="*60)
        mode_str = "MANUAL" if force else "AUTO"
        logger.info(f"📊 [{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] BẮT ĐẦU PHÂN TÍCH ({mode_str})...")
        logger.info("="*60)
        
        # Chạy phân tích và gửi telegram
        daily_report.main()
        
        logger.info("✅ Phân tích và gửi hoàn tất!")
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi phân tích: {e}", exc_info=True)

def run_schedule():
    """Hàm chạy Scheduler (Auto Mode)"""
    logger.info("🚀 KHỞI ĐỘNG SCHEDULER (Clean Architecture Version)...")
    logger.info("📅 Lịch trình: 3 Khung giờ Chiến lược (Thứ 2-6)")
    logger.info("🏖️ Bot nghỉ: Thứ 7, Chủ Nhật (Thị trường Forex/Gold đóng cửa)")
    logger.info("="*60)
    logger.info("🕐 KHUNG GIỜ 1: Báo cáo Đầu ngày (Phiên Á)")
    logger.info("   ⏰ 07:00 - Quét tin")
    logger.info("   📊 07:15 - Phân tích và gửi")
    logger.info("-" * 60)
    logger.info("🕐 KHUNG GIỜ 2: Chuẩn bị Phiên Âu (London Open)")
    logger.info("   ⏰ 13:30 - Quét tin")
    logger.info("   📊 13:45 - Phân tích và gửi")
    logger.info("-" * 60)
    logger.info("🕐 KHUNG GIỜ 3: Trước Phiên Mỹ (New York Open)")
    logger.info("   ⏰ 19:00 - Quét tin")
    logger.info("   📊 19:15 - Phân tích và gửi")
    logger.info("="*60)
    
    # Thiết lập lịch trình
    schedule.every().day.at("07:00").do(job_scan_news)
    schedule.every().day.at("07:15").do(job_analyze_and_send)
    
    schedule.every().day.at("13:30").do(job_scan_news)
    schedule.every().day.at("13:45").do(job_analyze_and_send)
    
    schedule.every().day.at("19:00").do(job_scan_news)
    schedule.every().day.at("19:15").do(job_analyze_and_send)
    
    # Alert
    logger.info("⚡ Thiết lập Real-time Alert: Chạy mỗi 15 phút")
    schedule.every(15).minutes.do(realtime_alert.main)

    # Economic Calendar
    logger.info("📅 Thiết lập Economic Calendar Worker: Chạy mỗi 5 phút")
    schedule.every(5).minutes.do(economic_worker.main)
    
    logger.info(f"✅ Đã thiết lập jobs.")
    logger.info("♾️  Bắt đầu vòng lặp tự động...")
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("\n⏹️  Dừng scheduler bởi người dùng")
    except Exception as e:
        logger.critical(f"🔥 LỖI NGHIÊM TRỌNG: {e}", exc_info=True)

def run_manual():
    """Chạy full flow thủ công (Scan -> Report -> Alert Test)"""
    logger.info("�️ [MANUAL MODE] Kích hoạt chạy thủ công toàn bộ quy trình...")
    
    logger.info("\n1️⃣ STEP 1: SCAN NEWS (Force Run)")
    job_scan_news(force=True)
    
    logger.info("\n2️⃣ STEP 2: DAILY REPORT (Force Run)")
    job_analyze_and_send(force=True)
    
    logger.info("\n3️⃣ STEP 3: REAL-TIME ALERT (Check once)")
    realtime_alert.main()
    
    logger.info("\n✅ [MANUAL MODE] Đã hoàn tất mọi tác vụ.")

def main():
    parser = argparse.ArgumentParser(description="Signals Bot Manager")
    parser.add_argument("--manual", action="store_true", help="Chạy thủ công ngay lập tức (Report + Alert)")
    parser.add_argument("--report", action="store_true", help="Chạy thủ công chỉ phần Report")
    parser.add_argument("--alert", action="store_true", help="Chạy thủ công chỉ phần Alert")
    
    args = parser.parse_args()

    if args.manual:
        run_manual()
    elif args.report:
        logger.info("🛠️ Running Manual Report...")
        job_scan_news(force=True)
        job_analyze_and_send(force=True)
    elif args.alert:
        logger.info("�️ Running Manual Alert...")
        realtime_alert.main()
    else:
        # Mặc định chạy Scheduler
        run_schedule()

if __name__ == "__main__":
    main()
