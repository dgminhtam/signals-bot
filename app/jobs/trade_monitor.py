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
        # Example position items: {'ticket': 123, 'type': 'BUY', 'volume': 0.1, 'profit': 10.5, 'sl': 2000.5, 'tp': 2010.5, ...}
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
                
                # 2. KIỂM TRA QUAN TRỌNG: Sync Real Values (Price, SL, TP) từ MT5
                # Mục đích: Fix lỗi hiển thị 'Points' (lệnh Sniper) thành 'Price'
                
                db_open_price = float(trade.get('open_price') or 0.0)
                mt5_open_price = float(mt5_pos.get('open_price') or 0.0)
                
                # SL/TP should be available from MT5 now (via updated Bridge)
                mt5_sl = float(mt5_pos.get('sl') or 0.0)
                mt5_tp = float(mt5_pos.get('tp') or 0.0)
                
                # Update nếu giá open thay đổi (fill lệnh) hoặc cần cập nhật SL/TP
                # Chú ý: Ta luôn update để đảm bảo đồng bộ mới nhất
                if mt5_open_price > 0:
                     await database.update_trade_details(ticket, mt5_open_price, mt5_sl, mt5_tp)
                     # logger.debug(f"      ✅ Synced details for #{ticket}") 
                
            else:
                # --- TRƯỜNG HỢP B: Trade không còn trên MT5 (Closed) ---
                # Gọi hàm get_trade_history để lấy giá chính xác
                logger.info(f"   -> Trade #{ticket} not found in MT5. Checking history...")
                
                history_data = await client.get_trade_history(ticket)
                
                if history_data and history_data.get('status') == 'CLOSED':
                    real_close_price = history_data.get('close_price', 0.0)
                    real_profit = history_data.get('profit', 0.0)
                    real_sl = history_data.get('sl')
                    real_tp = history_data.get('tp')
                    real_close_time = history_data.get('close_time') # Timestamp or None
                    
                    # Heuristic Logic for Close Reason
                    db_sl = float(trade.get('sl') or 0.0)
                    db_tp = float(trade.get('tp') or 0.0)
                    close_reason = "MANUAL/MT5"
                    
                    # Tolerance for "close enough" (e.g., slippage handling)
                    # For XAUUSD, 0.5 - 1.0 USD might be reasonable depending on broker.
                    # Let's use 1.0 as a safe buffer.
                    tolerance = 1.0 
                    
                    if real_profit > 0 and db_tp > 0 and abs(real_close_price - db_tp) <= tolerance:
                        close_reason = "HIT_TP"
                    elif real_profit < 0 and db_sl > 0 and abs(real_close_price - db_sl) <= tolerance:
                        close_reason = "HIT_SL"
                    elif real_profit > 0:
                        # Profit but not hitting TP exactly? Maybe Trailing Stop (which acts like SL but positive)?
                        # Or Manual Close in profit.
                        pass 
                    
                    await database.update_trade_exit(
                        ticket=ticket,
                        close_price=real_close_price,
                        profit=real_profit,
                        status='CLOSED',
                        close_reason=close_reason,
                        sl=real_sl,
                        tp=real_tp,
                        close_time=real_close_time
                    )
                    closed_count += 1
                    logger.info(f"      ✅ Synced CLOSED trade #{ticket}: Profit={real_profit} ({close_reason})")
                else:
                    # Không lấy được lịch sử
                    logger.warning(f"      ⚠️ History not found for #{ticket}. Keeping as OPEN to retry later.")
                    # Không update closed = 0.0 vội vàng.
        
        logger.info(f"✅ [TRADE MONITOR] Sync complete: {closed_count} closed, {updated_count} updated")
        
    except Exception as e:
        logger.error(f"❌ [TRADE MONITOR] Error during sync: {e}", exc_info=True)
