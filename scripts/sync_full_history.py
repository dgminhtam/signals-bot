import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from app.core import database
from app.services.mt5_bridge import MT5DataClient

# Setup Logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("FullSync")

async def main():
    logger.info("🔄 BẮT ĐẦU ĐỒNG BỘ TOÀN DIỆN (FULL SYNC) TỪ MT5...")
    
    await database.init_db()
    
    # 1. Lấy tất cả lệnh ĐÃ ĐÓNG từ DB
    trades = []
    async with database.get_db_connection() as conn:
        async with conn.execute("SELECT ticket FROM trade_history WHERE status='CLOSED'") as cursor:
            rows = await cursor.fetchall()
            trades = [row['ticket'] for row in rows]
            
    logger.info(f"📋 Tìm thấy {len(trades)} lệnh ĐÃ ĐÓNG trong DB cần kiểm tra.")
    
    client = MT5DataClient()
    count = 0
    
    for ticket in trades:
        # Gọi MT5 lấy dữ liệu gốc (đã cập nhật format mới)
        data = await client.get_trade_history(ticket)
        
        if data:
            # Update vào DB dùng hàm sync mới
            await database.sync_trade_data(
                ticket=ticket,
                open_price=data.get('open_price', 0.0),
                close_price=data.get('close_price', 0.0),
                profit=data.get('profit', 0.0),
                sl=data.get('sl', 0.0),
                tp=data.get('tp', 0.0),
                open_time=data.get('open_time', 0),
                close_time=data.get('close_time', 0)
            )
            count += 1
            logger.info(f"✅ Synced #{ticket}")
        else:
            logger.warning(f"⚠️ Không tìm thấy dữ liệu MT5 cho ticket #{ticket}")
            
    logger.info(f"🎉 Hoàn tất! Đã đồng bộ {count}/{len(trades)} lệnh.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
