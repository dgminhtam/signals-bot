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

async def sync_history_sltp():
    logger.info("🚀 Starting Historical SL/TP Sync...")
    
    # 1. Init DB
    await database.init_db()
    
    # 2. Get all closed trades (or all trades)
    # Since existing logic in monitoring might have missed SL/TP for closed trades
    # We should iterate all trades in history or just closed ones where SL/TP is 0.
    # For simplicity and robustness, let's fetch ALL Closed trades.
    
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
        db_sl = trade.get('sl')
        db_tp = trade.get('tp')
        
        # Optimization: If SL/TP already exists, maybe skip? 
        # But user requested "Create Script update SL/TP", implying they might be missing.
        # Let's force check MT5.
        
        history_data = await client.get_trade_history(ticket)
        
        if history_data:
            mt5_sl = history_data.get('sl')
            mt5_tp = history_data.get('tp')
            
            # Check if we have valid data to update
            if mt5_sl is not None and mt5_tp is not None:
                # Update DB
                # Note: database.update_trade_exit updates status/price/profit too.
                # We want to preserve existing data but just update SL/TP?
                # Actually update_trade_exit is designed for closure.
                # Let's use it to ensure everything is consistent, 
                # OR use a specific update query if we want to be safer.
                # But since previous step updated update_trade_exit to handle SL/TP, let's use it.
                # Pass existing values for others to avoid overwriting with defaults if any.
                
                await database.update_trade_exit(
                    ticket=ticket,
                    close_price=history_data.get('close_price', trade['close_price']),
                    profit=history_data.get('profit', trade['profit']),
                    status='CLOSED',
                    close_reason=trade.get('close_reason'), # Keep existing reason
                    sl=mt5_sl,
                    tp=mt5_tp
                )
                
                # Log success
                logger.info(f"✅ Updated Ticket #{ticket}: SL={mt5_sl}, TP={mt5_tp}")
                updated_count += 1
            else:
                logger.warning(f"⚠️ Ticket #{ticket}: MT5 returned no SL/TP data (Old EA format?)")
        else:
            logger.error(f"❌ Ticket #{ticket}: Not found in MT5 History.")
            
    logger.info(f"🏁 Sync Complete. Updated {updated_count}/{len(trades_to_update)} trades.")

if __name__ == "__main__":
    try:
        asyncio.run(sync_history_sltp())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal Error: {e}")
