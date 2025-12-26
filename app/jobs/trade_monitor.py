"""
Trade Monitor Worker - Synchronize trade status between Database and MT5

This worker runs periodically to:
1. Fetch open trades from database
2. Compare with current MT5 positions
3. Update database for closed trades (using history check)
4. Update floating profit for open trades
"""

import logging
from app.core import config, database
from app.services.mt5_bridge import MT5DataClient

logger = config.logger

async def main():
    """
    Main trade monitor function - syncs trade status between DB and MT5
    """
    logger.info("💾 [TRADE MONITOR] Starting trade synchronization...")
    
    try:
        # 1. Get open trades from database
        db_trades = await database.get_open_trades()
        if not db_trades:
            logger.info("   -> No open trades in database.")
            return
        
        logger.info(f"   -> Found {len(db_trades)} open trades in DB")
        
        # 2. Get current positions from MT5
        client = MT5DataClient()
        mt5_positions = await client.get_open_positions(symbol="ALL")
        
        # Create a dictionary for fast lookup: ticket -> position data
        # Example position items: {'ticket': 123, 'type': 'BUY', 'volume': 0.1, 'profit': 10.5, ...}
        mt5_map = {pos['ticket']: pos for pos in mt5_positions}
        
        logger.info(f"   -> Found {len(mt5_positions)} open positions in MT5")
        
        # 3. Synchronization Logic
        closed_count = 0
        updated_count = 0
        
        for trade in db_trades:
            ticket = trade['ticket']
            
            if ticket in mt5_map:
                # --- TRƯỜNG HỢP A: Trade vẫn còn trên MT5 (Open) ---
                mt5_pos = mt5_map[ticket]
                current_profit = mt5_pos.get('profit', 0.0)
                
                # 1. Update Floating Profit
                await database.update_trade_profit(ticket, current_profit)
                updated_count += 1
                
                # 2. KIỂM TRA QUAN TRỌNG: Update Open Price nếu đang là 0 (Lệnh Sniper/Relative)
                db_open_price = float(trade.get('open_price') or 0.0)
                mt5_open_price = mt5_pos.get('open_price')
                
                if mt5_open_price and (db_open_price == 0.0 or abs(db_open_price - mt5_open_price) > 0.0001):
                    await database.update_trade_entry_price(ticket, float(mt5_open_price))
                    logger.info(f"      ✅ Updated real entry price for Sniper trade #{ticket}: {mt5_open_price}") 
                
            else:
                # --- TRƯỜNG HỢP B: Trade không còn trên MT5 (Closed) ---
                # Gọi hàm get_trade_history để lấy giá chính xác
                logger.info(f"   -> Trade #{ticket} not found in MT5. Checking history...")
                
                history_data = await client.get_trade_history(ticket)
                
                if history_data and history_data.get('status') == 'CLOSED':
                    real_close_price = history_data.get('close_price', 0.0)
                    real_profit = history_data.get('profit', 0.0)
                    
                    await database.update_trade_exit(
                        ticket=ticket,
                        close_price=real_close_price,
                        profit=real_profit,
                        status='CLOSED'
                    )
                    closed_count += 1
                    logger.info(f"      ✅ Synced CLOSED trade #{ticket}: Profit={real_profit}")
                else:
                    # Không lấy được lịch sử
                    logger.warning(f"      ⚠️ History not found for #{ticket}. Keeping as OPEN to retry later.")
                    # Không update closed = 0.0 vội vàng.
        
        logger.info(f"✅ [TRADE MONITOR] Sync complete: {closed_count} closed, {updated_count} updated")
        
    except Exception as e:
        logger.error(f"❌ [TRADE MONITOR] Error during sync: {e}", exc_info=True)
