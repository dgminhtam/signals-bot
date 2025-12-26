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

    async def close_all_positions(self, symbol: str) -> bool:
        """
        Đóng TẤT CẢ lệnh của symbol (Async).
        Trả về True nếu sạch lệnh, False nếu vẫn còn.
        """
        logger.info(f"🛡️ DEFENSIVE MODE: Closing ALL positions for {symbol}...")
        
        # 1. Get List
        positions = await self.client.get_open_positions(symbol)
        if not positions:
            logger.info("   -> No open positions found.")
            return True
            
        # 2. Close Loop
        for pos in positions:
            ticket = pos['ticket']
            logger.info(f"   -> Closing Ticket #{ticket} ({pos['type']})...")
            
            res = await self._retry_action(self.client.close_order, ticket)
            if "FAIL" in str(res):
                 logger.error(f"   ❌ Failed to close #{ticket}: {res}")
        
        # 3. Double Check
        await asyncio.sleep(1.0) # Wait for MT5 update
        remaining = await self.client.get_open_positions(symbol)
        if remaining:
            logger.error(f"   ❌ WARNING: {len(remaining)} positions still open!")
            return False
            
        logger.info("   ✅ All positions closed successfully.")
        return True
        
    async def analyze_and_trade(self):
        """
        Chiến lược (Async version):
        """
        logger.info(f"🤖 Starting Analysis for {self.symbol} (Vol: {self.volume})...")

        # 1. Get Signal from DB
        signal_data = await database.get_latest_valid_signal(self.symbol, ttl_minutes=60)
        
        if not signal_data:
            logger.info("⏸️ No valid signal in DB (News/AI). Waiting...")
            return "WAIT_NO_SIGNAL"

        source = signal_data.get('source', 'UNKNOWN')
        signal_type = signal_data.get('signal_type', 'WAIT')
        score = signal_data.get('score', 0)
        signal_id = signal_data.get('id')
        
        logger.info(f"📥 Received Signal: {signal_type} from {source} (Score: {score}, ID: {signal_id})")
        
        # ===== CASE A: NEWS SIGNAL (FAST TRACK) =====
        if source == 'NEWS':
            logger.info("⚡ NEWS SIGNAL detected! Executing FAST TRACK...")
            
            df, _ = await get_market_data(self.symbol)
            if df is None or df.empty:
                logger.error("❌ Failed to get market price for News Order.")
                return "FAIL_NO_PRICE"
            current_price = df['Close'].iloc[-1]
            
            # Use NEWS config
            sl = 0.0
            tp = 0.0
            
            if signal_type == "BUY":
                sl = current_price - config.TRADE_NEWS_SL
                tp = current_price + config.TRADE_NEWS_TP
            elif signal_type == "SELL":
                sl = current_price + config.TRADE_NEWS_SL
                tp = current_price - config.TRADE_NEWS_TP
            else:
                 return "WAIT"

            # ===== SMART POSITION MANAGEMENT =====
            # Check for opposite positions and close weak NEWS trades
            logger.info("🔍 Checking for opposite positions...")
            open_positions = await self.client.get_open_positions(self.symbol)
            
            if open_positions:
                opposite_type = "SELL" if signal_type == "BUY" else "BUY"
                opposite_positions = [pos for pos in open_positions if pos['type'] == opposite_type]
                
                if opposite_positions:
                    logger.info(f"   -> Found {len(opposite_positions)} opposite {opposite_type} position(s)")
                    
                    for pos in opposite_positions:
                        ticket = pos['ticket']
                        metadata = await database.get_trade_metadata(ticket)
                        
                        # Decision Tree
                        should_close = False
                        reason = ""
                        
                        if metadata is None:
                            # No signal metadata (Sniper/Straddle/Manual)
                            reason = "PROTECTED (Sniper/Straddle/Manual - No Signal ID)"
                        elif metadata['source'] == 'AI_REPORT':
                            reason = "PROTECTED (AI_REPORT - Long-term trend)"
                        elif metadata['source'] == 'NEWS' and metadata['score'] >= 8:
                            reason = f"PROTECTED (High-impact NEWS - Score {metadata['score']})"
                        elif metadata['source'] == 'NEWS' and metadata['score'] < 8:
                            should_close = True
                            reason = f"CLOSABLE (Weak NEWS - Score {metadata['score']})"
                        else:
                            reason = f"PROTECTED (Unknown source: {metadata['source']})"
                        
                        logger.info(f"   -> Ticket #{ticket}: {reason}")
                        
                        if should_close:
                            logger.info(f"   ⚔️ Closing opposite weak NEWS position #{ticket}...")
                            close_result = await self.client.close_order(ticket)
                            
                            if "SUCCESS" in close_result:
                                # Update database status
                                await database.update_trade_exit(
                                    ticket=ticket,
                                    close_price=0.0,  # Actual close price not available from close command
                                    profit=pos.get('profit', 0.0),
                                    status='CLOSED'
                                )
                                logger.info(f"   ✅ Closed #{ticket} successfully (Profit: {pos.get('profit', 0.0):.2f})")
                            else:
                                logger.error(f"   ❌ Failed to close #{ticket}: {close_result}")
                else:
                    logger.info("   -> No opposite positions found")
            else:
                logger.info("   -> No open positions")
            # Execute via Retry (Use NEWS volume)
            logger.info(f"🚀 Executing NEWS {signal_type} | @{current_price:.2f} | SL:{sl} TP:{tp} | Vol:{config.TRADE_NEWS_VOLUME}")
            result = await self._retry_action(self.client.execute_order, self.symbol, signal_type, config.TRADE_NEWS_VOLUME, sl, tp)
            
            # Save to Database & Mark as processed
            if signal_id and "SUCCESS" in result:
                # Parse ticket from response: "SUCCESS|123456"
                try:
                    ticket = int(result.split("|")[1])
                    await database.save_trade_entry(
                        ticket, signal_id, self.symbol, signal_type, 
                        config.TRADE_NEWS_VOLUME, current_price, sl, tp
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to save trade to DB: {e}")
                
                await database.mark_signal_processed(signal_id)
                logger.info(f"✅ Signal #{signal_id} marked as processed.")
            
            return result

        # ===== CASE B: AI REPORT SIGNAL (NORMAL TRACK) =====
        upcoming_news = await database.check_upcoming_high_impact_news(minutes=30)
        if upcoming_news:
            logger.warning(f"⛔ DỪNG GIAO DỊCH (AI): Sắp có tin mạnh \"{upcoming_news}\".")
            return "WAIT_NEWS_EVENT"

        recent_news = await database.check_recent_high_impact_news(minutes=15)
        if recent_news:
             logger.warning(f"⛔ DỪNG GIAO DỊCH (AI): Vừa có tin mạnh \"{recent_news}\".")
             return "WAIT_POST_NEWS"

        # Get Market Data
        df, src_name = await get_market_data(self.symbol)
        if df is None or df.empty: return "FAIL_NO_DATA"
        
        current_price = df['Close'].iloc[-1]
        
        # Volume Check
        try:
             vol_sma20 = df['Volume'].tail(20).mean()
             current_vol = df['Volume'].iloc[-1]
             prev_vol = df['Volume'].iloc[-2]
             
             if (current_vol <= vol_sma20) and (prev_vol <= vol_sma20):
                  logger.warning("⚠️ Volume Low (< SMA20). AI Signal Weak.")
                  return "WAIT_LOW_VOLUME"
        except: pass
        
        # Extract AI-generated SL/TP from database
        db_entry = signal_data.get('entry_price')
        db_sl = signal_data.get('stop_loss')
        db_tp = signal_data.get('take_profit')
        
        # Determine SL/TP: Use AI values if available, else fallback to REPORT config
        sl = 0.0
        tp = 0.0
        
        if db_sl and db_tp and db_sl != 0 and db_tp != 0:
            # Use AI-generated levels
            sl = db_sl
            tp = db_tp
            logger.info(f"📊 Using AI-generated levels: SL={sl:.2f}, TP={tp:.2f}")
        else:
            # Fallback to REPORT config
            logger.warning("⚠️ AI SL/TP missing or invalid. Using REPORT config fallback.")
            
            if signal_type == "BUY":
                 sl = current_price - config.TRADE_REPORT_SL
                 tp = current_price + config.TRADE_REPORT_TP
            elif signal_type == "SELL":
                 sl = current_price + config.TRADE_REPORT_SL
                 tp = current_price - config.TRADE_REPORT_TP
            else:
                return "WAIT"
            
        logger.info(f"🚀 Executing AI {signal_type} (Verified) | Vol: {config.TRADE_REPORT_VOLUME}")
        result = await self._retry_action(self.client.execute_order, self.symbol, signal_type, config.TRADE_REPORT_VOLUME, sl, tp)
        
        # Save to Database & Mark as processed
        if signal_id and "SUCCESS" in result:
            # Parse ticket from response
            try:
                ticket = int(result.split("|")[1])
                await database.save_trade_entry(
                    ticket, signal_id, self.symbol, signal_type,
                    config.TRADE_REPORT_VOLUME, current_price, sl, tp
                )
            except Exception as e:
                logger.error(f"❌ Failed to save trade to DB: {e}")
            
            await database.mark_signal_processed(signal_id)
            logger.info(f"✅ Signal #{signal_id} marked as processed.")
        
        return result

    async def process_news_signal(self, news_data: dict):
        """
        Xử lý phản ứng với tin tức (Async)
        """
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
            is_safe = await self.close_all_positions(self.symbol)
            if not is_safe:
                logger.critical("⛔ CRITICAL: FAILED TO CLOSE POSITIONS! ABORTING ENTRY!")
                return 

        # ===== STEP 3: OFFENSIVE (Sniper Entry) =====
        if score >= 8:
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
                        config.TRADE_SNIPER_VOLUME, 0.0, sl_points, tp_points
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to save SNIPER trade to DB: {e}")
            
        else:
            logger.info(f"   -> Score {score} < 8. No automated entry.")

    async def place_straddle_orders(self, distance: float = None, sl: float = None, tp: float = None, volume: float = None) -> List[str]:
        """
        Đặt 2 lệnh chờ (Buy Stop / Sell Stop) cách giá hiện tại một khoảng distance.
        Strategy: News Straddle / Trap Trading.
        
        Args:
            distance: USD price distance from current (default: config.TRADE_CALENDAR_DIST)
            sl: Stop loss in USD (default: config.TRADE_CALENDAR_SL)
            tp: Take profit in USD (default: config.TRADE_CALENDAR_TP)
            volume: Trading volume (default: config.TRADE_CALENDAR_VOLUME)
        """
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
                    vol, buy_stop_price, buy_sl, buy_tp
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
                     vol, sell_stop_price, sell_sl, sell_tp
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
            except Exception as e:
                logger.error(f"   ❌ Error deleting #{t}: {e}")

