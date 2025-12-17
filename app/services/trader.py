"""
AutoTrader - AI-Sentiment + Fibonacci/Volume Strategy
"""
import logging
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
        
    def analyze_and_trade(self):
        """
        AI-Sentiment Trading Strategy:
        1. Lấy AI Sentiment từ Database
        2. Lấy Market Data (Price + Volume)
        3. Xác định Direction (AI Trend + Score)
        4. Volume Confirmation
        5. Fibonacci SL/TP
        6. Execute
        """
        logger.info(f"🤖 Starting AI-Sentiment Analysis for {self.symbol} (Vol: {self.volume})...")
        
        # ===== STEP 0: CHECK NEWS FILTER (PRE & POST) =====
        upcoming_news = database.check_upcoming_high_impact_news(minutes=30)
        if upcoming_news:
            logger.warning(f"⛔ DỪNG GIAO DỊCH: Sắp có tin mạnh \"{upcoming_news}\" trong 30 phút tới.")
            return "WAIT_NEWS_EVENT"

        recent_news = database.check_recent_high_impact_news(minutes=15)
        if recent_news:
             logger.warning(f"⛔ DỪNG GIAO DỊCH: Vừa có tin mạnh \"{recent_news}\" trong 15 phút qua. Chờ thị trường ổn định.")
             return "WAIT_POST_NEWS"

        # ===== STEP 1: GET AI SENTIMENT & CHECK TTL =====
        latest_report = database.get_latest_report()
        
        if not latest_report:
            logger.warning("⚠️ No AI report found. Cannot trade.")
            return "WAIT_NO_SENTIMENT"
            
        try:
             created_at_str = latest_report.get('created_at')
             if created_at_str:
                 report_time = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
                 if datetime.utcnow() - report_time > timedelta(minutes=180):
                     logger.warning(f"⏳ Signal Expired! Report time: {created_at_str}. Old > 180 mins.")
                     return "WAIT_SIGNAL_EXPIRED"
        except Exception as e:
            logger.error(f"⚠️ Error checking signal TTL: {e}")

        ai_trend = latest_report.get('trend', 'NEUTRAL')
        ai_score = latest_report.get('sentiment_score', 0)
        
        logger.info(f"📊 AI Report: Trend={ai_trend}, Score={ai_score}")
        
        # ===== STEP 2: GET MARKET DATA =====
        df, source = get_market_data(self.symbol)
        if df is None or df.empty:
            logger.error("❌ No market data received.")
            return "FAIL_NO_DATA"
        
        current_price = df['Close'].iloc[-1]
        logger.info(f"💰 Current Price: {current_price:.2f} (Source: {source})")
        
        # ===== STEP 3: DETERMINE DIRECTION =====
        signal = "WAIT"
        trend_upper = ai_trend.upper()
        
        if ("BULLISH" in trend_upper) and (ai_score > 0):
            signal = "BUY"
        elif ("BEARISH" in trend_upper) and (ai_score < 0):
            signal = "SELL"
        else:
            logger.info(f"⏸️ AI Signal Unclear: {ai_trend} (Score: {ai_score}) → WAIT")
            return "WAIT_WEAK_SIGNAL"
        
        # ===== STEP 3.1: SMART ENTRY CHECK =====
        ai_entry = latest_report.get('entry_price', 0.0)
        if ai_entry and ai_entry > 0:
            diff = abs(current_price - ai_entry)
            if diff > 3.0: 
                 logger.warning(f"⚠️ Price too far from AI Entry (Diff > 3). Current: {current_price:.2f}, AI: {ai_entry}.")
                 return "WAIT_BAD_PRICE"
        
        # ===== STEP 4: VOLUME CONFIRMATION =====
        try:
            if len(df) >= 20:
                # 4.1 Volume Analysis
                vol_sma20 = df['Volume'].tail(20).mean()
                current_vol = df['Volume'].iloc[-1]
                prev_vol = df['Volume'].iloc[-2]
                
                # 4.2 Price Analysis (SMA20)
                price_sma20 = df['Close'].tail(20).mean()
                
                # 4.3 Fibo Levels
                fibo = calculate_fibonacci_levels(df, window=120)
                sup = fibo.get('0.0', 0) # Support (min) ?? No, 1.0 is Low usually in that dict logic
                # Actually calculate_fibonacci_levels returns dict mapping '0.0' to High, '1.0' to Low usually or vice versa depending on logic.
                # In charter.py: '0.0': price_high, '1.0': price_low.
                # Let's just log the full important levels.
                
                logger.info(f"💾 MARKET INDICATORS:")
                logger.info(f"   • Price: {current_price:.2f} (SMA20: {price_sma20:.2f})")
                logger.info(f"   • Volume: {current_vol} (Prev: {prev_vol}, SMA20: {vol_sma20:.0f})")
                if fibo:
                    logger.info(f"   • Fibo Support (100%): {fibo.get('1.0', 0):.2f}")
                    logger.info(f"   • Fibo Res (0%): {fibo.get('0.0', 0):.2f}")
                    logger.info(f"   • Fibo Golden (61.8%): {fibo.get('0.618', 0):.2f}")
                
                if (current_vol <= vol_sma20) and (prev_vol <= vol_sma20):
                    logger.warning("⚠️ Volume Low (< SMA20). Signal Weak.")
                    return "WAIT_LOW_VOLUME"
                else:
                    logger.info("✅ Volume Confirmed (> SMA20).")
        except Exception as e:
            logger.error(f"⚠️ Indicator Check Error: {e}")
        
        # ===== STEP 5: DETERMINE SL/TP =====
        ai_sl = latest_report.get('stop_loss', 0.0)
        ai_tp = latest_report.get('take_profit', 0.0)
        
        sl = 0.0
        tp = 0.0
        
        if (ai_sl > 0 and ai_tp > 0):
            sl = ai_sl
            tp = ai_tp
            logger.info(f"✅ Using AI Levels: SL={sl}, TP={tp}")
        else:
            # Fallback
            FALLBACK_SL_PIPS = 5.0
            FALLBACK_TP_PIPS = 10.0
            
            # Simple Fibo Support/Resist Check could go here
            if signal == "BUY":
                sl = current_price - FALLBACK_SL_PIPS
                tp = current_price + FALLBACK_TP_PIPS
            elif signal == "SELL":
                sl = current_price + FALLBACK_SL_PIPS
                tp = current_price - FALLBACK_TP_PIPS
        
        # ===== STEP 6: EXECUTE =====
        if signal in ["BUY", "SELL"]:
            logger.info(f"🚀 Executing {signal} (Vol: {self.volume}) | SL: {sl:.2f} | TP: {tp:.2f}")
            response = self.client.execute_order(self.symbol, signal, self.volume, sl, tp)
            return response
            
        return "WAIT"

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
            
        # 2. DEFENSIVE: Check Existing Positions
        positions = self.client.get_open_positions(self.symbol)
        for pos in positions:
            pos_type = pos['type'] # "BUY" or "SELL"
            ticket = pos['ticket']
            
            # Nếu lệnh ngược chiều tin (Tin BUY mà đang SELL)
            if pos_type != signal_direction:
                logger.warning(f"⚠️ [DANGER] Holding {pos_type} (#{ticket}) against NEWS DIRECTION ({signal_direction})!")
                
                # Tùy chọn: Auto Cut Loss nếu tin quá mạnh (>8)
                if score >= 8:
                    logger.warning(f"   -> EMERGENCY CLOSE (#{ticket}) due to High Impact News!")
                    self.client.close_order(ticket)
            else:
                logger.info(f"   -> Position #{ticket} ({pos_type}) is SAFE (Matches News).")

        # 3. OFFENSIVE: Sniper Entry if Score >= 8 (High Confidence)
        if score >= 8:
            logger.info(f"⚔️ [OFFENSIVE] High Impact News detected (Score {score}). Preparing Sniper Entry...")
            
            # Get Current Price
            df, _ = get_market_data(self.symbol)
            if df is None or df.empty:
                logger.error("   -> Failed to get price for Sniper Entry.")
                return

            current_price = df['Close'].iloc[-1]
            
            # Sniper Params: SL 10, TP 20
            sl = 0.0
            tp = 0.0
            if signal_direction == "BUY":
                sl = current_price - 10.0
                tp = current_price + 20.0
            else:
                sl = current_price + 10.0
                tp = current_price - 20.0
                
            logger.info(f"🚀 SNIPER EXECUTION: {signal_direction} @ {current_price:.2f} (SL: {sl}, TP: {tp})")
            response = self.client.execute_order(self.symbol, signal_direction, self.volume, sl, tp)
            logger.info(f"   -> Sniper Result: {response}")
            
        else:
            logger.info(f"   -> Score {score} < 8. No automated entry.")
