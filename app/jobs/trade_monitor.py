"""
Trade Monitor Worker - Synchronize trade status between Database and MT5

This worker runs periodically to:
1. Fetch open trades from database
2. Compare with current MT5 positions
3. Update database for closed trades (negative check)
4. Update floating profit for open trades
"""

import logging
from datetime import datetime
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
        
        # Create a set of MT5 ticket numbers for fast lookup
        mt5_tickets = {pos['ticket'] for pos in mt5_positions}
        logger.info(f"   -> Found {len(mt5_positions)} open positions in MT5")
        
        # 3. Synchronization Logic (Negative Check)
        closed_count = 0
        updated_count = 0
        
        for trade in db_trades:
            ticket = trade['ticket']
            
            # Check if trade still exists in MT5
            if ticket not in mt5_tickets:
                # Trade closed (TP/SL/Manual) - Update database
                logger.info(f"   -> Trade #{ticket} closed (not in MT5). Updating DB...")
                await database.update_trade_exit(
                    ticket=ticket,
                    close_price=0.0,  # We don't have close price from get_open_positions
                    profit=0.0,       # Profit also not available here
                    status='CLOSED'
                )
                closed_count += 1
            else:
                # Trade still open - Update floating profit
                mt5_pos = next((p for p in mt5_positions if p['ticket'] == ticket), None)
                if mt5_pos:
                    current_profit = mt5_pos.get('profit', 0.0)
                    await database.update_trade_profit(ticket, current_profit)
                    updated_count += 1
        
        logger.info(f"✅ [TRADE MONITOR] Sync complete: {closed_count} closed, {updated_count} updated")
        
    except Exception as e:
        logger.error(f"❌ [TRADE MONITOR] Error during sync: {e}", exc_info=True)
