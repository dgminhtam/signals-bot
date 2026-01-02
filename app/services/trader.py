import logging
import asyncio
import time
from typing import List
from datetime import datetime, timedelta
from app.services.market_data_service import get_market_data
from app.services.mt5_bridge import MT5DataClient
from app.core import database
from app.core import config

logger = config.logger

class AutoTrader:
    def __init__(self, symbol="XAUUSD", volume=None):
        self.symbol = symbol
        # Use Config Volume if not provided
        self.volume = volume if volume else config.TRADE_VOLUME
        self.client = MT5DataClient()
    
    def _get_points(self, price_delta: float) -> float:
        """
        Helper: Convert USD Price Movement to MT5 Points for XAUUSD.
        XAUUSD has 2 decimal places (e.g., 2650.50).
        1 USD = 100 Points (e.g., 10.0 USD = 1000.0 Points)
        """
        return price_delta * 100.0
        

    async def _retry_action(self, func, *args, max_retries=3, delay=1.0):
        """
        Helper thực hiện retry nếu gặp lỗi hoặc phản hồi FAIL (Async)
        func phải là coroutine function
        """
        for attempt in range(max_retries):
            try:
                # Call async function
                result = await func(*args)
                
                # Check MT5 FAIL response
                if isinstance(result, str) and "FAIL" in result:
                    logger.warning(f"⚠️ Action failed: {result}. Retrying ({attempt+1}/{max_retries})...")
                    await asyncio.sleep(delay)
                    continue
                    
                return result
            except Exception as e:
                logger.warning(f"⚠️ Action Exception: {e}. Retrying ({attempt+1}/{max_retries})...")
                await asyncio.sleep(delay)
                
        return "FAIL|MAX_RETRIES"

    async def check_market_conflict(self, signal_type: str) -> bool:
        """
        Kiểm tra xung đột: Trả về True nếu tồn tại lệnh ngược chiều (Opened positions).
        Signal BUY -> Check if SELL exists.
        Signal SELL -> Check if BUY exists.
        """
        try:
            positions = await self.client.get_open_positions(self.symbol)
            if not positions:
                return False
                
            opposite_type = "SELL" if signal_type == "BUY" else "BUY"
            
            # Check if any position matches opposite type
            for pos in positions:
                if pos['type'] == opposite_type:
                    return True
                    
            return False
        except Exception as e:
            logger.error(f"Error checking conflict: {e}")
            return False  # Assume no conflict on error to avoid blocking, or True to be safe? Default False for now.

    async def close_all_positions(self, symbol: str, reason: str = "STRATEGY_EXIT", except_type: str = None) -> bool:
        """
        Đóng lệnh của symbol, trừ loại lệnh trong except_type.
        """
        logger.info(f"🛡️ DEFENSIVE MODE: Closing positions for {symbol} (Reason: {reason}, Except: {except_type})...")
        
        # 1. Get List
        positions = await self.client.get_open_positions(symbol)
        if not positions:
            return True
            
        # 2. Close Loop
        for pos in positions:
            # Giữ lại lệnh cùng chiều
            if except_type and pos['type'] == except_type:
                logger.info(f"   -> Keeping #{pos['ticket']} ({pos['type']}) - Matches Signal.")
                continue

            ticket = pos['ticket']
            logger.info(f"   -> Closing Ticket #{ticket} ({pos['type']})...")
            
            res = await self._retry_action(self.client.close_order, ticket)
            if "FAIL" in str(res):
                 logger.error(f"   ❌ Failed to close #{ticket}: {res}")
            else:
                 # Update DB immediately
                 await database.update_trade_exit(
                     ticket=ticket,
                     close_price=0.0, # Will be synced by monitor later if precise needed, or 0 here
                     profit=pos.get('profit', 0.0),
                     status='CLOSED',
                     close_reason=reason
                 )
        
        # 3. Double Check
        await asyncio.sleep(1.0) # Wait for MT5 update
        remaining = await self.client.get_open_positions(symbol)
        
        # Chỉ coi là thất bại nếu còn lệnh KHÁC except_type
        unwanted = [p for p in remaining if not (except_type and p['type'] == except_type)]
        
        if unwanted:
            logger.error(f"   ❌ WARNING: {len(unwanted)} unwanted positions still open!")
            return False
            
        return True
        
    async def analyze_and_trade(self):
        """
        Chiến lược (Batch Processing & Conflict Guard implementation):
        """
        logger.info(f"🤖 Starting Analysis for {self.symbol} (Vol: {self.volume})...")

        # 1. Get ALL Valid Signals from DB (Sorted by Quality)
        signals_list = await database.get_all_valid_signals(self.symbol, ttl_minutes=config.SIGNAL_TTL_MINUTES)
        
        if not signals_list:
            logger.info("⏸️ No valid signals in DB (News/AI). Waiting...")
            return "WAIT_NO_SIGNAL"

        logger.info(f"📥 Found {len(signals_list)} valid signals. Processing batch...")
        
        results = []

        # 2. Iterate through signals
        for signal_data in signals_list:
            source = signal_data.get('source', 'UNKNOWN')
            signal_type = signal_data.get('signal_type', 'WAIT')
            score = signal_data.get('score', 0)
            signal_id = signal_data.get('id')
            
            logger.info(f"👉 Processing Signal #{signal_id}: {signal_type} from {source} (Score: {score})")

            # --- CONFLICT GUARD LOGIC ---
            is_conflict = await self.check_market_conflict(signal_type)
            
            if is_conflict:
                logger.warning(f"   ⚠️ Conflict detected! Existing opposite positions found.")
                
                # Decision Matrix
                if abs(score) >= 8:
                    logger.info("   🔥 STRONG SIGNAL (>=8). Switching Trend!")
                    
                    # Action: Close all old positions
                    close_success = await self.close_all_positions(self.symbol, reason="CONFLICT_REVERSE")
                    if not close_success:
                        logger.error("   ❌ Failed to close old positions. Skipping this signal safety.")
                        await database.mark_signal_processed(signal_id)
                        results.append(f"SKIP_CLOSE_FAIL_{signal_id}")
                        continue
                        
                    logger.info("   ✅ Old positions cleared. Proceeding to entry...")
                else:
                    logger.info(f"   🛡️ WEAK SIGNAL (<8). Ignored to protect existing trend.")
                    await database.mark_signal_processed(signal_id)
                    results.append(f"IGNORED_WEAK_{signal_id}")
                    continue  # Skip to next signal
            else:
                 logger.info("   ✅ No conflict. Safe to execute.")

            # --- EXECUTION LOGIC (Refactored from original) ---
            
            # CASE A: NEWS SIGNAL
            if source == 'NEWS':
                if not config.ENABLE_STRATEGY_NEWS:
                     logger.info("   ⛔ Strategy NEWS is DISABLED. Skipping.")
                     await database.mark_signal_processed(signal_id)
                     continue

                df, _ = await get_market_data(self.symbol)
                if df is None or df.empty:
                    logger.error("❌ Failed to get market price for News Order.")
                    continue 
                current_price = df['Close'].iloc[-1]
                
                sl = 0.0
                tp = 0.0
                
                if signal_type == "BUY":
                    sl = current_price - config.TRADE_NEWS_SL
                    tp = current_price + config.TRADE_NEWS_TP
                elif signal_type == "SELL":
                    sl = current_price + config.TRADE_NEWS_SL
                    tp = current_price - config.TRADE_NEWS_TP
                
                logger.info(f"   🚀 Executing NEWS {signal_type} | SL:{sl} TP:{tp}")
                result = await self._retry_action(self.client.execute_order, self.symbol, signal_type, config.TRADE_NEWS_VOLUME, sl, tp)
                
                if signal_id and "SUCCESS" in result:
                    try:
                        ticket = int(result.split("|")[1])
                        await database.save_trade_entry(
                            ticket, signal_id, self.symbol, signal_type, 
                            config.TRADE_NEWS_VOLUME, current_price, sl, tp,
                            strategy='NEWS'
                        )
                    except Exception as e:
                        logger.error(f"❌ Failed to save trade to DB: {e}")
                    
                    await database.mark_signal_processed(signal_id)
                    results.append(result)
                else:
                    logger.error(f"   ❌ Execution Failed: {result}")
            
            # CASE B: AI REPORT SIGNAL
            elif source == 'AI_REPORT':
                if not config.ENABLE_STRATEGY_REPORT:
                     logger.info("   ⛔ Strategy REPORT is DISABLED. Skipping.")
                     await database.mark_signal_processed(signal_id)
                     continue

                # Check News Constraints only for AI signals? (Optional, kept from original logic)
                upcoming_news = await database.check_upcoming_high_impact_news(minutes=30)
                if upcoming_news:
                    logger.warning(f"   ⛔ DỪNG GIAO DỊCH (AI): Sắp có tin mạnh \"{upcoming_news}\".")
                    await database.mark_signal_processed(signal_id) 
                    results.append("SKIP_NEWS_EVENT")
                    continue

                df, src_name = await get_market_data(self.symbol)
                if df is None or df.empty: 
                    continue
                
                current_price = df['Close'].iloc[-1]
                
                # Signal SL/TP/Entry
                db_sl = signal_data.get('stop_loss')
                db_tp = signal_data.get('take_profit')
                db_entry = signal_data.get('entry_price')
                
                sl = 0.0
                tp = 0.0
                
                if db_sl and db_tp and db_sl != 0 and db_tp != 0:
                    sl = db_sl
                    tp = db_tp
                else:
                    # Fallback
                    if signal_type == "BUY":
                         sl = current_price - config.TRADE_REPORT_SL
                         tp = current_price + config.TRADE_REPORT_TP
                    elif signal_type == "SELL":
                         sl = current_price + config.TRADE_REPORT_SL
                         tp = current_price - config.TRADE_REPORT_TP
                
                # Xác định Entry Price cho lệnh Pending
                exec_price = 0.0
                if "LIMIT" in signal_type or "STOP" in signal_type:
                    if db_entry and db_entry > 0:
                        exec_price = db_entry
                    else:
                        logger.error(f"❌ Lệnh {signal_type} thiếu Entry Price. Bỏ qua.")
                        await database.mark_signal_processed(signal_id)
                        continue
                
                logger.info(f"   🚀 Executing AI {signal_type} | Price: {exec_price} | Vol: {config.TRADE_REPORT_VOLUME}")
                result = await self._retry_action(
                    self.client.execute_order, 
                    self.symbol, 
                    signal_type, 
                    config.TRADE_REPORT_VOLUME, 
                    sl, 
                    tp,
                    exec_price
                )
                
                if signal_id and "SUCCESS" in result:
                    try:
                        ticket = int(result.split("|")[1])
                        await database.save_trade_entry(
                            ticket, signal_id, self.symbol, signal_type,
                            config.TRADE_REPORT_VOLUME, current_price, sl, tp,
                            strategy='REPORT'
                        )
                    except Exception as e:
                        logger.error(f"❌ Failed to save trade to DB: {e}")
                    
                    await database.mark_signal_processed(signal_id)
                    results.append(result)
        
        return results

    async def process_news_signal(self, news_data: dict):
        """
        Xử lý phản ứng với tin tức (Async)
        """
        if not config.ENABLE_STRATEGY_NEWS:
            logger.info("⛔ Strategy NEWS is DISABLED globally. Ignoring event.")
            return

        score = news_data.get('score', 0)
        trend = news_data.get('trend', 'NEUTRAL').upper()
        title = news_data.get('title', 'News Event')
        
        logger.info(f"⚡ [NEWS REACTOR] Processing: '{title}' (Trend: {trend}, Score: {score}/10)")

        # 1. Determine Direction
        signal_direction = "NONE"
        if "BULLISH" in trend or "POSITIVE" in trend:
            signal_direction = "BUY"
        elif "BEARISH" in trend or "NEGATIVE" in trend:
            signal_direction = "SELL"
            
        if signal_direction == "NONE":
            logger.info("   -> News trend neutral/mixed. No action.")
            return

        # ===== STEP 1: SAVE SIGNAL TO DB =====
        try:
            await database.save_trade_signal(self.symbol, signal_direction, "NEWS", float(score))
            logger.info(f"   💾 Saved Signal: {signal_direction} (Score {score})")
        except Exception as e:
            logger.error(f"   ❌ DB Save Error: {e}")

        # ===== STEP 2: DEFENSIVE =====
        is_safe = True
        if score >= 8:
            is_safe = await self.close_all_positions(self.symbol, reason="NEWS_DEFENSE", except_type=signal_direction)
            if not is_safe:
                logger.critical("⛔ CRITICAL: FAILED TO CLOSE POSITIONS! ABORTING ENTRY!")
                return 

        # ===== STEP 3: OFFENSIVE (Sniper Entry) =====
        if score >= 8:
            if not config.ENABLE_STRATEGY_SNIPER:
                logger.info("   🛡️ Sniper Strategy is DISABLED. Skipping offensive entry.")
            else:
                logger.info(f"⚔️ [OFFENSIVE] High Impact News detected (Score {score}). Preparing Sniper Entry (Fire-and-Forget)...")
                
                # Use SNIPER config and convert to MT5 Points
                sl_points = self._get_points(config.TRADE_SNIPER_SL)
                tp_points = self._get_points(config.TRADE_SNIPER_TP)
                
                logger.info(f"🚀 SNIPER EXECUTION: {signal_direction} (SL: {config.TRADE_SNIPER_SL} USD / {sl_points} pts, TP: {config.TRADE_SNIPER_TP} USD / {tp_points} pts)")
                
                # Call relative execution immediately (Use SNIPER volume)
                response = await self._retry_action(
                    self.client.execute_order_relative, 
                    self.symbol, signal_direction, config.TRADE_SNIPER_VOLUME, sl_points, tp_points
                )
                
                logger.info(f"   -> Sniper Result: {response}")
                
                # Save to Database
                if "SUCCESS" in response:
                    try:
                        ticket = int(response.split("|")[1])
                        # For relative orders, we don't have exact prices yet, save as 0
                        await database.save_trade_entry(
                            ticket, None, self.symbol, signal_direction,
                            config.TRADE_SNIPER_VOLUME, 0.0, sl_points, tp_points,
                            strategy='SNIPER'
                        )
                    except Exception as e:
                        logger.error(f"❌ Failed to save SNIPER trade to DB: {e}")
            
        else:
            logger.info(f"   -> Score {score} < 8. No automated entry.")

    async def place_straddle_orders(self, distance: float = None, sl: float = None, tp: float = None, volume: float = None) -> List[str]:
        """
        Đặt 2 lệnh chờ (Buy Stop / Sell Stop) cách giá hiện tại một khoảng distance.
        Strategy: News Straddle / Trap Trading.
        
        """
        if not config.ENABLE_STRATEGY_CALENDAR:
             logger.warning("   🛑 STRATEGY_CALENDAR is DISABLED. Skipping Straddle setup.")
             return []

        Args:
            distance: USD price distance from current (default: config.TRADE_CALENDAR_DIST)
            sl: Stop loss in USD (default: config.TRADE_CALENDAR_SL)
            tp: Take profit in USD (default: config.TRADE_CALENDAR_TP)
            volume: Trading volume (default: config.TRADE_CALENDAR_VOLUME)
        """
        if not config.ENABLE_STRATEGY_CALENDAR:
             logger.warning("   🛑 STRATEGY_CALENDAR is DISABLED. Skipping Straddle setup.")
             return []

        # Use CALENDAR config defaults if not provided
        distance = distance if distance is not None else config.TRADE_CALENDAR_DIST
        sl = sl if sl is not None else config.TRADE_CALENDAR_SL
        tp = tp if tp is not None else config.TRADE_CALENDAR_TP
        vol = volume if volume is not None else config.TRADE_CALENDAR_VOLUME
        
        logger.info(f"🕸️ Preparing STRADDLE Strategy via MT5 (Distance: {distance} USD, SL: {sl} USD, TP: {tp} USD, Vol: {vol})...")
        
        # 1. Get Current Market Price
        df, _ = await get_market_data(self.symbol)
        if df is None or df.empty:
            logger.error("❌ Failed to get market data for Straddle.")
            return []
            
        current_price = df['Close'].iloc[-1]
        
        # Use USD price directly (no pip conversion needed)
        buy_stop_price = current_price + distance
        sell_stop_price = current_price - distance
        
        # Calculate SL/TP
        # Buy Stop: SL below entry, TP above
        buy_sl = buy_stop_price - sl
        buy_tp = buy_stop_price + tp
        
        # Sell Stop: SL above entry, TP below
        sell_sl = sell_stop_price + sl
        sell_tp = sell_stop_price - tp
        
        tickets = []
        
        # 2. Place BUY STOP
        logger.info(f"   -> Placing BUY STOP @ {buy_stop_price:.2f} (SL: {buy_sl:.2f}, TP: {buy_tp:.2f})")
        res_buy = await self.client.execute_order(
            self.symbol, "BUY_STOP", vol, buy_sl, buy_tp, price=buy_stop_price
        )
        if "SUCCESS" in res_buy:
            ticket_str = res_buy.split("|")[1]
            tickets.append(ticket_str)
            logger.info(f"     ✅ BUY STOP Placed: #{ticket_str}")
            
            # Save to Database
            try:
                ticket = int(ticket_str)
                await database.save_trade_entry(
                    ticket, None, self.symbol, "BUY_STOP",
                    vol, buy_stop_price, buy_sl, buy_tp,
                    strategy='CALENDAR'
                )
            except Exception as e:
                logger.error(f"❌ Failed to save BUY_STOP to DB: {e}")
        else:
             logger.error(f"     ❌ BUY STOP Failed: {res_buy}")
             
        # 3. Place SELL STOP
        logger.info(f"   -> Placing SELL STOP @ {sell_stop_price:.2f} (SL: {sell_sl:.2f}, TP: {sell_tp:.2f})")
        res_sell = await self.client.execute_order(
            self.symbol, "SELL_STOP", vol, sell_sl, sell_tp, price=sell_stop_price
        )
        if "SUCCESS" in res_sell:
             ticket_str = res_sell.split("|")[1]
             tickets.append(ticket_str)
             logger.info(f"     ✅ SELL STOP Placed: #{ticket_str}")
             
             # Save to Database
             try:
                 ticket = int(ticket_str)
                 await database.save_trade_entry(
                     ticket, None, self.symbol, "SELL_STOP",
                     vol, sell_stop_price, sell_sl, sell_tp,
                     strategy='CALENDAR'
                 )
             except Exception as e:
                 logger.error(f"❌ Failed to save SELL_STOP to DB: {e}")
        else:
             logger.error(f"     ❌ SELL STOP Failed: {res_sell}")
             
        return tickets

    async def cleanup_pending_orders(self, tickets: List[str]):
        """
        Xóa các lệnh pending chưa khớp theo danh sách ticket.
        """
        logger.info(f"🧹 Clearing Pending Orders: {tickets}")
        for t in tickets:
            if not t: continue
            try:
                ticket_int = int(t)
                res = await self.client.delete_order(ticket_int)
                logger.info(f"   -> Delete #{t}: {res}")
                
                # Update DB status to CANCELLED instead of keeping it OPEN
                if "SUCCESS" in res:
                    await database.update_trade_exit(
                        ticket=ticket_int,
                        close_price=0.0,
                        profit=0.0,
                        status='CANCELLED',
                        close_reason='STRADDLE_EXPIRED'
                    )
            except Exception as e:
                logger.error(f"   ❌ Error deleting #{t}: {e}")
