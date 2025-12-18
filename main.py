"""
Scheduler - Tự động quét tin và phân tích theo 3 khung giờ chiến lược

Script này sẽ:
- Quét tin và phân tích vào 3 khung giờ: 07:00, 13:30, 19:00
- Chỉ chạy từ Thứ 2 đến Thứ 6 (thị trường Forex/Gold nghỉ cuối tuần)
- Gửi báo cáo qua Telegram
"""

import asyncio
import argparse
import sys
import logging
from datetime import datetime

# APScheduler Imports
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core import config
from app.services import news_crawler
from app.jobs import daily_report
from app.jobs import realtime_alert
from app.jobs import economic_worker
from app.services.trader import AutoTrader

logger = config.logger

def is_weekday():
    """Kiểm tra có phải ngày làm việc không (Thứ 2-6)"""
    return datetime.now().weekday() < 5  # 0-4 là Thứ 2-6

async def job_scan_news(force=False):
    """Job quét tin từ RSS (Async)"""
    # Kiểm tra cuối tuần (nếu không force)
    if not force and not is_weekday():
        logger.info("🏖️ Cuối tuần (Thứ 7/CN) - Thị trường Forex/Gold nghỉ, bot nghỉ!")
        return
    
    try:
        logger.info("="*60)
        mode_str = "MANUAL" if force else "AUTO"
        logger.info(f"🕐 [{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] BẮT ĐẦU QUÉT TIN ({mode_str})...")
        logger.info("="*60)
        
        # Quét tin từ RSS (Await async function)
        await news_crawler.get_gold_news()
        
        logger.info("✅ Quét tin hoàn tất!")
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi quét tin: {e}", exc_info=True)

async def job_analyze_and_send(force=False):
    """Job phân tích và gửi telegram (Async)"""
    # Kiểm tra cuối tuần (nếu không force)
    if not force and not is_weekday():
        logger.info("🏖️ Cuối tuần (Thứ 7/CN) - Thị trường Forex/Gold nghỉ, bot nghỉ!")
        return
    
    try:
        logger.info("="*60)
        mode_str = "MANUAL" if force else "AUTO"
        logger.info(f"📊 [{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] BẮT ĐẦU PHÂN TÍCH ({mode_str})...")
        logger.info("="*60)
        
        # Chạy phân tích và gửi telegram (Await)
        await daily_report.main()
        
        logger.info("✅ Phân tích và gửi hoàn tất!")
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi phân tích: {e}", exc_info=True)

async def job_auto_trade(force=False):
    """Job tự động giao dịch (Auto Trader) (Async)"""
    # AutoTrader cũng chỉ chạy ngày thường
    if not force and not is_weekday():
        logger.info("🏖️ Cuối tuần - AutoTrader nghỉ.")
        return

    try:
        logger.info("="*60)
        mode = "MANUAL" if force else "AUTO"
        logger.info(f"🤖 [{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] STARING AUTO TRADER ({mode})...")
        
        # Init & Run
        trader = AutoTrader("XAUUSD")
        await trader.analyze_and_trade()
        
        logger.info("✅ Auto Trader Job Completed.")
        logger.info("="*60)

    except Exception as e:
        logger.error(f"❌ Lỗi Auto Trader: {e}", exc_info=True)

async def start_scheduler():
    """Hàm chạy Scheduler (Auto Mode) với APScheduler"""
    logger.info("🚀 KHỞI ĐỘNG SCHEDULER (AsyncIO + APScheduler Version)...")
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
    
    # Khởi tạo Scheduler
    scheduler = AsyncIOScheduler()
    
    # --- SCAN NEWS JOBS (Async) ---
    scheduler.add_job(job_scan_news, CronTrigger(hour=7, minute=0))
    scheduler.add_job(job_scan_news, CronTrigger(hour=13, minute=30))
    scheduler.add_job(job_scan_news, CronTrigger(hour=19, minute=0))
    
    # --- ANALYZE JOBS (Async) ---
    scheduler.add_job(job_analyze_and_send, CronTrigger(hour=7, minute=15))
    scheduler.add_job(job_analyze_and_send, CronTrigger(hour=13, minute=45))
    scheduler.add_job(job_analyze_and_send, CronTrigger(hour=19, minute=15))
    
    # --- REALTIME ALERT (1 phút) ---
    logger.info("⚡ Thiết lập Real-time Alert: Chạy mỗi 1 phút (HFT Mode)")
    scheduler.add_job(realtime_alert.main, IntervalTrigger(minutes=1), max_instances=1, coalesce=True)

    # --- ECONOMIC CALENDAR (5 phút) ---
    logger.info("📅 Thiết lập Economic Calendar Worker: Chạy mỗi 5 phút")
    scheduler.add_job(economic_worker.main, IntervalTrigger(minutes=5), max_instances=1, coalesce=True)
    
    # --- AUTO TRADER (Each Hour at :02) ---
    logger.info("🤖 Thiết lập Auto Trader: Chạy mỗi giờ (phút 02)")
    scheduler.add_job(job_auto_trade, CronTrigger(minute='2'), max_instances=1, coalesce=True)
    
    logger.info(f"✅ Đã thiết lập jobs.")
    logger.info("♾️  Bắt đầu vòng lặp sự kiện (Event Loop)...")
    
    from app.core import database
    await database.init_db()
    
    scheduler.start()
    
    try:
        # Keep alive forever
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n⏹️  Dừng scheduler bởi người dùng")
        scheduler.shutdown()
    except Exception as e:
        logger.critical(f"🔥 LỖI NGHIÊM TRỌNG: {e}", exc_info=True)
        scheduler.shutdown()

async def run_manual_async(report_only=False, alert_only=False, trade_only=False, crawler_only=False, calendar_only=False):
    """Chạy full flow thủ công (Async Wrapper)"""
    
    from app.core import database
    await database.init_db()
    
    if report_only:
        logger.info("🛠️ Running Manual Report...")
        await job_scan_news(force=True)
        await job_analyze_and_send(force=True)
        return

    if alert_only:
        logger.info("⚡ Running Manual Alert...")
        await realtime_alert.main()
        return

    if trade_only:
        logger.info("🤖 Running Manual Trader...")
        await job_auto_trade(force=True)
        return
        
    if crawler_only:
         logger.info("📰 Running Manual Crawler...")
         await job_scan_news(force=True)
         return
         
    if calendar_only:
         logger.info("📅 Running Manual Economic Calendar...")
         await economic_worker.main()
         return

    # Default: Full Check
    logger.info("🛠️ [MANUAL MODE] Kích hoạt chạy thủ công toàn bộ quy trình...")
    logger.info("\n1️⃣ STEP 1: SCAN NEWS (Force Run)")
    await job_scan_news(force=True)
    
    logger.info("\n2️⃣ STEP 2: DAILY REPORT (Force Run)")
    await job_analyze_and_send(force=True)
    
    logger.info("\n3️⃣ STEP 3: REAL-TIME ALERT (Check once)")
    await realtime_alert.main()
    
    logger.info("\n✅ [MANUAL MODE] Đã hoàn tất mọi tác vụ.")

def main():
    parser = argparse.ArgumentParser(description="Signals Bot Manager (AsyncIO)")
    parser.add_argument("--manual", action="store_true", help="Chạy thủ công ngay lập tức (Report + Alert)")
    parser.add_argument("--report", action="store_true", help="Chạy thủ công chỉ phần Report")
    parser.add_argument("--alert", action="store_true", help="Chạy thủ công chỉ phần Alert")
    parser.add_argument("--crawler", action="store_true", help="Chạy thủ công chỉ phần News Crawler")
    parser.add_argument("--trade", action="store_true", help="Chạy thủ công Auto Trader")
    parser.add_argument("--calendar", action="store_true", help="Chạy thủ công Economic Calendar")
    
    args = parser.parse_args()

    try:
        if args.manual:
            asyncio.run(run_manual_async())
        elif args.report:
            asyncio.run(run_manual_async(report_only=True))
        elif args.alert:
            asyncio.run(run_manual_async(alert_only=True))
        elif args.trade:
            asyncio.run(run_manual_async(trade_only=True))
        elif args.crawler:
             asyncio.run(run_manual_async(crawler_only=True))
        elif args.calendar:
             asyncio.run(run_manual_async(calendar_only=True))
        else:
            # Chạy Scheduler (Async Mode)
            asyncio.run(start_scheduler())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"FATAL ERROR: {e}", exc_info=True)

if __name__ == "__main__":
    main()
