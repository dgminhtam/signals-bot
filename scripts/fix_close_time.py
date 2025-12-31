import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core import config, database
from app.services.mt5_bridge import MT5DataClient

# Setup simple logger to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

async def fix_close_time():
    logger.info("🚀 Starting Fix Close Time & SL/TP...")
    
    # 1. Init DB
    await database.init_db()
    
    # 2. Get all closed trades
    trades_to_update = []
    try:
        async with database.get_db_connection() as conn:
            async with conn.execute("SELECT * FROM trade_history WHERE status = 'CLOSED'") as cursor:
                 rows = await cursor.fetchall()
                 trades_to_update = [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"❌ Failed to fetch trades from DB: {e}")
        return

    if not trades_to_update:
        logger.info("✅ No closed trades found in Database.")
        return

    logger.info(f"📋 Found {len(trades_to_update)} closed trades to check.")
    
    client = MT5DataClient()
    updated_count = 0
    
    for trade in trades_to_update:
        ticket = trade['ticket']
        
        # Checking MT5 for accurate data
        history_data = await client.get_trade_history(ticket)
        
        if history_data:
            mt5_sl = history_data.get('sl')
            mt5_tp = history_data.get('tp')
            mt5_close_time = history_data.get('close_time') # Timestamp
            
            # Update DB with accurate time and SL/TP
            await database.update_trade_exit(
                ticket=ticket,
                close_price=history_data.get('close_price', trade['close_price']),
                profit=history_data.get('profit', trade['profit']),
                status='CLOSED',
                close_reason=trade.get('close_reason'), # Keep existing reason
                sl=mt5_sl,
                tp=mt5_tp,
                close_time=mt5_close_time
            )
            
            # Log success
            if mt5_close_time:
                 import datetime
                 utc_str = datetime.datetime.fromtimestamp(mt5_close_time, tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                 local_str = datetime.datetime.fromtimestamp(mt5_close_time).strftime('%Y-%m-%d %H:%M:%S')
                 
                 logger.info(f"✅ Ticket #{ticket} Fixed.")
                 logger.info(f"   -> DB Saved (UTC): {utc_str}")
                 logger.info(f"   -> Real Time (VN): {local_str}")
            else:
                 logger.info(f"✅ Updated #{ticket} (No Time Data)")
            updated_count += 1
        else:
            logger.error(f"❌ Ticket #{ticket}: Not found in MT5 History.")
            
    logger.info(f"🏁 Fix Complete. Updated {updated_count}/{len(trades_to_update)} trades.")

if __name__ == "__main__":
    try:
        asyncio.run(fix_close_time())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal Error: {e}")
