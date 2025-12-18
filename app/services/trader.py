"""
AutoTrader - AI-Sentiment + Fibonacci/Volume Strategy (AsyncIO)
"""
import logging
import asyncio
import time
from datetime import datetime, timedelta
from app.services.charter import get_market_data
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
        
        logger.info(f"📥 Received Signal: {signal_type} from {source} (Score: {score})")
        
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
            return await self._retry_action(self.client.execute_order, self.symbol, signal_type, self.volume, sl, tp)

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
        return await self._retry_action(self.client.execute_order, self.symbol, signal_type, self.volume, sl, tp)

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
            logger.info(f"⚔️ [OFFENSIVE] High Impact News detected (Score {score}). Preparing Sniper Entry...")
            
            # Get Current Price
            df, _ = await get_market_data(self.symbol)
            if df is None or df.empty:
                logger.error("   -> Failed to get price for Sniper Entry.")
                return

            current_price = df['Close'].iloc[-1]
            
            sl = 0.0
            tp = 0.0
            SL_DIST = 10.0
            TP_DIST = 20.0
            
            if signal_direction == "BUY":
                sl = current_price - SL_DIST
                tp = current_price + TP_DIST
            else:
                sl = current_price + SL_DIST
                tp = current_price - TP_DIST
                
            logger.info(f"🚀 SNIPER EXECUTION: {signal_direction} @ {current_price:.2f} (SL: {sl}, TP: {tp})")
            
            response = await self._retry_action(
                self.client.execute_order, 
                self.symbol, signal_direction, self.volume, sl, tp
            )
            
            logger.info(f"   -> Sniper Result: {response}")
            
        else:
            logger.info(f"   -> Score {score} < 8. No automated entry.")
