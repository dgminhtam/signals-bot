"""
AutoTrader - AI-Sentiment + Fibonacci/Volume Strategy
"""
import logging
import time
from datetime import datetime, timedelta
from app.services.charter import get_market_data, calculate_fibonacci_levels
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
        
    def _retry_action(self, func, *args, max_retries=3, delay=1.0):
        """
        Helper thực hiện retry nếu gặp lỗi hoặc phản hồi FAIL
        """
        for attempt in range(max_retries):
            try:
                result = func(*args)
                
                # Check MT5 FAIL response
                if isinstance(result, str) and "FAIL" in result:
                    logger.warning(f"⚠️ Action failed: {result}. Retrying ({attempt+1}/{max_retries})...")
                    time.sleep(delay)
                    continue
                    
                return result
            except Exception as e:
                logger.warning(f"⚠️ Action Exception: {e}. Retrying ({attempt+1}/{max_retries})...")
                time.sleep(delay)
                
        return "FAIL|MAX_RETRIES"

    def close_all_positions(self, symbol: str) -> bool:
        """
        Đóng TẤT CẢ lệnh của symbol.
        Trả về True nếu sạch lệnh, False nếu vẫn còn.
        """
        logger.info(f"🛡️ DEFENSIVE MODE: Closing ALL positions for {symbol}...")
        
        # 1. Get List
        positions = self.client.get_open_positions(symbol)
        if not positions:
            logger.info("   -> No open positions found.")
            return True
            
        # 2. Close Loop
        for pos in positions:
            ticket = pos['ticket']
            logger.info(f"   -> Closing Ticket #{ticket} ({pos['type']})...")
            
            res = self._retry_action(self.client.close_order, ticket)
            if "FAIL" in str(res):
                 logger.error(f"   ❌ Failed to close #{ticket}: {res}")
        
        # 3. Double Check
        time.sleep(1.0) # Wait for MT5 update
        remaining = self.client.get_open_positions(symbol)
        if remaining:
            logger.error(f"   ❌ WARNING: {len(remaining)} positions still open!")
            return False
            
        logger.info("   ✅ All positions closed successfully.")
        return True
        
    def analyze_and_trade(self):
        """
        Chiến lược:
        1. Lấy tín hiệu từ DB (Ưu tiên NEWS > AI REPORT).
        2. Nếu NEWS: Thực thi ngay (Sniper/Fast).
        3. Nếu AI: Kiểm tra thêm Technical (Volume, Price) -> Execute.
        """
        logger.info(f"🤖 Starting Analysis for {self.symbol} (Vol: {self.volume})...")

        # ===== STEP 0: NEWS FILTER (Giữ nguyên check Pre/Post news cho AI, nhưng nếu Signal là NEWS thì bỏ qua check này?)
        # Logic: Nếu Signal Source == NEWS, nghĩa là ta ĐANG phản ứng với tin, nên không bị chặn bởi bộ lọc tin.
        # Nếu Signal Source == AI_REPORT, thì cần tuân thủ bộ lọc tin.
        
        # 1. Get Signal from DB
        signal_data = database.get_latest_valid_signal(self.symbol, ttl_minutes=60)
        
        if not signal_data:
            logger.info("⏸️ No valid signal in DB (News/AI). Waiting...")
            return "WAIT_NO_SIGNAL"

        source = signal_data.get('source', 'UNKNOWN')
        signal_type = signal_data.get('signal_type', 'WAIT') # BUY/SELL
        score = signal_data.get('score', 0)
        
        logger.info(f"📥 Received Signal: {signal_type} from {source} (Score: {score})")
        
        # ===== CASE A: NEWS SIGNAL (FAST TRACK) =====
        if source == 'NEWS':
            # Với tin tức, ta bỏ qua phân tích kỹ thuật rườm rà
            logger.info("⚡ NEWS SIGNAL detected! Executing FAST TRACK...")
            
            # Tuy nhiên vẫn cần check giá hiện tại để tính SL/TP nếu trong DB chưa có (DB chỉ lưu direction)
            df, _ = get_market_data(self.symbol)
            if df is None or df.empty:
                logger.error("❌ Failed to get market price for News Order.")
                return "FAIL_NO_PRICE"
            current_price = df['Close'].iloc[-1]
            
            # Param cho News (Rộng hơn bình thường)
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
            return self._retry_action(self.client.execute_order, self.symbol, signal_type, self.volume, sl, tp)

        # ===== CASE B: AI REPORT SIGNAL (NORMAL TRACK) =====
        # Check News Filter (Chỉ áp dụng cho AI Signal)
        upcoming_news = database.check_upcoming_high_impact_news(minutes=30)
        if upcoming_news:
            logger.warning(f"⛔ DỪNG GIAO DỊCH (AI): Sắp có tin mạnh \"{upcoming_news}\".")
            return "WAIT_NEWS_EVENT"

        recent_news = database.check_recent_high_impact_news(minutes=15)
        if recent_news:
             logger.warning(f"⛔ DỪNG GIAO DỊCH (AI): Vừa có tin mạnh \"{recent_news}\".")
             return "WAIT_POST_NEWS"

        # (Phần còn lại giữ nguyên Logic Technical cũ...)
        
        # Get Market Data
        df, src_name = get_market_data(self.symbol)
        if df is None or df.empty: return "FAIL_NO_DATA"
        
        current_price = df['Close'].iloc[-1]
        
        # Validate Entry (Smart Entry)
        # AI signal in DB doesn't retain entry_price explicitly in trade_signals table (it has score/type).
        # We might need to look up the report details if we want entry price, but `trade_signals` is simplified.
        # Assuming current price is "good enough" if score is high, or verify with volume.
        
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
        return self._retry_action(self.client.execute_order, self.symbol, signal_type, self.volume, sl, tp)

    def process_news_signal(self, news_data: dict):
        """
        Xử lý phản ứng với tin tức (Breaking News / Calendar)
        Input: {'score': 0-10, 'trend': 'BULLISH', ...}
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
            database.save_trade_signal(self.symbol, signal_direction, "NEWS", float(score))
            logger.info(f"   💾 Saved Signal: {signal_direction} (Score {score})")
        except Exception as e:
            logger.error(f"   ❌ DB Save Error: {e}")

        # ===== STEP 2: DEFENSIVE (Close All OLD Positions if High Impact) =====
        # Nếu Score >= 8 (Rất mạnh) -> Đóng hết lệnh cũ để tránh biến động ngược
        # Hoặc nếu phát hiện lệnh ngược chiều (nhưng ở đây Close All cho an toàn theo yêu cầu)
        is_safe = True
        if score >= 8:
            is_safe = self.close_all_positions(self.symbol)
            if not is_safe:
                logger.critical("⛔ CRITICAL: FAILED TO CLOSE POSITIONS! ABORTING ENTRY!")
                return # STOP HERE

        # ===== STEP 3: OFFENSIVE (Sniper Entry) =====
        if score >= 8:
            logger.info(f"⚔️ [OFFENSIVE] High Impact News detected (Score {score}). Preparing Sniper Entry...")
            
            # Get Current Price
            df, _ = get_market_data(self.symbol)
            if df is None or df.empty:
                logger.error("   -> Failed to get price for Sniper Entry.")
                return

            current_price = df['Close'].iloc[-1]
            
            # Sniper Params: Wide SL/TP for volatility
            # Example: SL 10 pips, TP 20 pips (Gold)
            # 1 pip Gold = 0.1? No, 1.0 usually $1 movement.
            # Let's say SL $10, TP $20 movement.
            
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
            
            # Sử dụng Retry Action cho lệnh quan trọng
            response = self._retry_action(
                self.client.execute_order, 
                self.symbol, signal_direction, self.volume, sl, tp
            )
            
            logger.info(f"   -> Sniper Result: {response}")
            
        else:
            logger.info(f"   -> Score {score} < 8. No automated entry.")
