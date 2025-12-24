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
trade_logger = config.trade_logger

class AutoTrader:
    def __init__(self, symbol="XAUUSD", volume=None):
        self.symbol = symbol
        # Use Config Volume if not provided
        self.volume = volume if volume else config.TRADE_VOLUME
        self.client = MT5DataClient()
        
    def _log_execution(self, mode: str, type_str: str, vol: float, price: float, sl: float, tp: float, response: str):
        """
        Ghi log giao dịch vào file trades.log
        Format: TIME | MODE | SYMBOL | TYPE | VOL | PRICE | SL | TP | RESULT | TICKET | RAW_RESPONSE
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Determine Result & Ticket
            result = "FAIL"
            ticket = "N/A"
            
            if "SUCCESS" in response:
                result = "SUCCESS"
                parts = response.split("|")
                if len(parts) > 1:
                    ticket = parts[1]
            
            log_line = (
                f"{timestamp} | {mode} | {self.symbol} | {type_str} | {vol} | "
                f"{price:.2f} | {sl:.2f} | {tp:.2f} | {result} | {ticket} | {response}"
            )
            
            trade_logger.info(log_line)
        except Exception as e:
            logger.error(f"❌ Error writing to Trade Log: {e}")

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
            
            # Param cho News
            SL_PIPS = 10.0
            TP_PIPS = 20.0
            
            sl = 0.0
            tp = 0.0
            
            if signal_type == "BUY":
                sl = current_price - SL_PIPS
                tp = current_price + TP_PIPS
            elif signal_type == "SELL":
                sl = current_price + SL_PIPS
                tp = current_price - TP_PIPS
            else:
                 return "WAIT"

            # Execute via Retry
            logger.info(f"🚀 Executing NEWS {signal_type} | @{current_price:.2f} | SL:{sl} TP:{tp}")
            result = await self._retry_action(self.client.execute_order, self.symbol, signal_type, self.volume, sl, tp)
            
            # LOGGING
            self._log_execution(
                "NEWS_FAST", signal_type, self.volume, current_price, sl, tp, result
            )
            
            # Mark as processed
            if signal_id and "SUCCESS" in result:
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
        
        # SL/TP Calculation (Standard)
        FALLBACK_SL = 5.0
        FALLBACK_TP = 10.0
        sl = 0.0
        tp = 0.0
        
        if signal_type == "BUY":
             sl = current_price - FALLBACK_SL
             tp = current_price + FALLBACK_TP
        elif signal_type == "SELL":
             sl = current_price + FALLBACK_SL
             tp = current_price - FALLBACK_TP
        else:
            return "WAIT"
            
        logger.info(f"🚀 Executing AI {signal_type} (Verified) | Vol: {self.volume}")
        result = await self._retry_action(self.client.execute_order, self.symbol, signal_type, self.volume, sl, tp)
        
        # LOGGING
        self._log_execution(
            "AI_REPORT", signal_type, self.volume, current_price, sl, tp, result
        )
        
        # Mark as processed
        if signal_id and "SUCCESS" in result:
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
            
            # FAST TRACK: NO MARKET DATA FETCHING
            # Use relative points for SL/TP (Assuming XAUUSD Standard)
            # 1000 Points = 100 Pips (if 1 pip = 10 points) ~ $10 Price Move (if 1 point = 0.01)
            SL_POINTS = 1000.0 
            TP_POINTS = 2000.0
            
            logger.info(f"🚀 SNIPER EXECUTION: {signal_direction} (Rel. Pts - SL: {SL_POINTS}, TP: {TP_POINTS})")
            
            # Call relative execution immediately
            response = await self._retry_action(
                self.client.execute_order_relative, 
                self.symbol, signal_direction, self.volume, SL_POINTS, TP_POINTS
            )
            
            logger.info(f"   -> Sniper Result: {response}")
            
            # LOGGING
            self._log_execution(
                "SNIPER", signal_direction, self.volume, 0.0, SL_POINTS, TP_POINTS, response
            )
            
        else:
            logger.info(f"   -> Score {score} < 8. No automated entry.")

    async def place_straddle_orders(self, distance_pips: float = 20.0, sl_pips: float = 10.0, tp_pips: float = 30.0) -> List[str]:
        """
        Đặt 2 lệnh chờ (Buy Stop / Sell Stop) cách giá hiện tại một khoảng distance_pips.
        Strategy: News Straddle / Trap Trading.
        """
        logger.info(f"🕸️ Preparing STRADDLE Strategy via MT5 (Dist: {distance_pips} pips)...")
        
        # 1. Get Current Market Price
        df, _ = await get_market_data(self.symbol)
        if df is None or df.empty:
            logger.error("❌ Failed to get market data for Straddle.")
            return []
            
        current_price = df['Close'].iloc[-1]
        
        # Convert Pips to Price (Assuming XAUUSD 0.1 pip or Standard 0.0001)
        # TODO: Dynamic Pip Value based on Symbol digits. For now XAUUSD ~ 0.1 per pip? 
        # Actually standard for XAUUSD is 0.01 or 0.1 depending on broker. 
        # Often 1 pip = 0.1 USD. Let's assume input pips are standard pips.
        # If symbol is XAUUSD, usually 2 digits -> 0.1 is 1 pip? Or 0.01?
        # Let's generalize: 1 pip = 10 * Point. If Point=0.01, Pip=0.1.
        
        pip_value = 0.1 if "XAU" in self.symbol else 0.0001
        if "JPY" in self.symbol and "XAU" not in self.symbol: pip_value = 0.01
        
        distance_price = distance_pips * pip_value
        sl_price_dist = sl_pips * pip_value
        tp_price_dist = tp_pips * pip_value
        
        buy_stop_price = current_price + distance_price
        sell_stop_price = current_price - distance_price
        
        # Calculate SL/TP
        # Buy Stop: SL below entry, TP above
        buy_sl = buy_stop_price - sl_price_dist
        buy_tp = buy_stop_price + tp_price_dist
        
        # Sell Stop: SL above entry, TP below
        sell_sl = sell_stop_price + sl_price_dist
        sell_tp = sell_stop_price - tp_price_dist
        
        tickets = []
        
        # 2. Place BUY STOP
        logger.info(f"   -> Placing BUY STOP @ {buy_stop_price:.2f} (SL: {buy_sl:.2f}, TP: {buy_tp:.2f})")
        res_buy = await self.client.execute_order(
            self.symbol, "BUY_STOP", self.volume, buy_sl, buy_tp, price=buy_stop_price
        )
        if "SUCCESS" in res_buy:
            ticket = res_buy.split("|")[1]
            tickets.append(ticket)
            logger.info(f"     ✅ BUY STOP Placed: #{ticket}")
        else:
             logger.error(f"     ❌ BUY STOP Failed: {res_buy}")
        
        # LOGGING BUY STOP
        self._log_execution(
            "STRADDLE", "BUY_STOP", self.volume, buy_stop_price, buy_sl, buy_tp, res_buy
        )
             
        # 3. Place SELL STOP
        logger.info(f"   -> Placing SELL STOP @ {sell_stop_price:.2f} (SL: {sell_sl:.2f}, TP: {sell_tp:.2f})")
        res_sell = await self.client.execute_order(
            self.symbol, "SELL_STOP", self.volume, sell_sl, sell_tp, price=sell_stop_price
        )
        if "SUCCESS" in res_sell:
             ticket = res_sell.split("|")[1]
             tickets.append(ticket)
             logger.info(f"     ✅ SELL STOP Placed: #{ticket}")
        else:
             logger.error(f"     ❌ SELL STOP Failed: {res_sell}")
        
        # LOGGING SELL STOP
        self._log_execution(
            "STRADDLE", "SELL_STOP", self.volume, sell_stop_price, sell_sl, sell_tp, res_sell
        )
             
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

