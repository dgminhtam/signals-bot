"""
Worker chuyên biệt cho việc quét Lịch Kinh Tế (Async).
"""
import sys
import os
import asyncio
from app.core import database

# Thêm path để import module từ root
sys.path.append(os.getcwd())

from app.core import config
from app.services.economic_calendar import EconomicCalendarService

logger = config.logger

async def main():
    try:
        logger.info("📅 [ECONOMIC WORKER] Đang kiểm tra Lịch Kinh Tế...")
        
        # Đảm bảo Table tồn tại (nếu chạy lần đầu)
        await database.init_db()
        
        service = EconomicCalendarService()
        await service.process_calendar_alerts()
        
        logger.info("📅 [ECONOMIC WORKER] Hoàn tất.")
        
    except Exception as e:
        logger.error(f"❌ Economic Worker Error: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
