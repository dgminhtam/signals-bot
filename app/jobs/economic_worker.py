"""
Worker chuyên biệt cho việc quét Lịch Kinh Tế (Economic Calendar).
Chạy độc lập với Realtime Alert để đảm bảo không bị block hoặc ảnh hưởng flow khác.
Nên chạy Sát giờ tin hoặc định kỳ (vd: mỗi 5-10 phút).
"""
import sys
import os

# Thêm path để import module từ root
sys.path.append(os.getcwd())

from app.core import config
from app.core import database
from app.services.economic_calendar import EconomicCalendarService

logger = config.logger

def main():
    try:
        logger.info("📅 [ECONOMIC WORKER] Đang kiểm tra Lịch Kinh Tế...")
        
        # Đảm bảo Table tồn tại (nếu chạy lần đầu)
        # database.init_db() # Có thể uncomment nếu chạy worker này độc lập hoàn toàn mà chưa init DB
        
        service = EconomicCalendarService()
        service.process_calendar_alerts()
        
        logger.info("📅 [ECONOMIC WORKER] Hoàn tất.")
        
    except Exception as e:
        logger.error(f"❌ Economic Worker Error: {e}", exc_info=True)

if __name__ == "__main__":
    main()
