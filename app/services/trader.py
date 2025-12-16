"""
AutoTrader - AI-Sentiment + Fibonacci/Volume Strategy
"""
import logging
from datetime import datetime, timedelta
from app.services.charter import get_market_data, calculate_fibonacci_levels
from app.services.mt5_bridge import MT5DataClient
from app.core import database

logger = logging.getLogger(__name__)

class AutoTrader:
    def __init__(self, symbol="XAUUSD", volume=0.01):
        self.symbol = symbol
        self.volume = volume
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
        logger.info(f"🤖 Starting AI-Sentiment Analysis for {self.symbol}...")
        
        # ===== STEP 0: CHECK NEWS FILTER (PRE & POST) =====
        # 0.1 Upcoming News (30 mins)
        upcoming_news = database.check_upcoming_high_impact_news(minutes=30)
        if upcoming_news:
            logger.warning(f"⛔ DỪNG GIAO DỊCH: Sắp có tin mạnh \"{upcoming_news}\" trong 30 phút tới.")
            return "WAIT_NEWS_EVENT"

        # 0.2 Post News (15 mins) - NEW
        # Tránh market biến động mạnh ngay sau tin
        recent_news = database.check_recent_high_impact_news(minutes=15)
        if recent_news:
             logger.warning(f"⛔ DỪNG GIAO DỊCH: Vừa có tin mạnh \"{recent_news}\" trong 15 phút qua. Chờ thị trường ổn định.")
             return "WAIT_POST_NEWS"

        # ===== STEP 1: GET AI SENTIMENT & CHECK TTL =====
        latest_report = database.get_latest_report()
        
        if not latest_report:
            logger.warning("⚠️ No AI report found in database. Cannot trade without sentiment.")
            return "WAIT_NO_SENTIMENT"
            
        # 1.1 Check Time-To-Live (TTL) - NEW
        # Nếu report quá cũ (> 180 phút), không trade theo tin cũ
        try:
             created_at_str = latest_report.get('created_at')
             if created_at_str:
                 # SQLite default CURRENT_TIMESTAMP is UTC 'YYYY-MM-DD HH:MM:SS'
                 report_time = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
                 # Compare with UTC now
                 if datetime.utcnow() - report_time > timedelta(minutes=180):
                     logger.warning(f"⏳ Signal Expired! Report time: {created_at_str} (UTC). Old > 180 mins. Skip.")
                     return "WAIT_SIGNAL_EXPIRED"
        except Exception as e:
            logger.error(f"⚠️ Error checking signal TTL: {e}. Proceeding with caution.")

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
        
        # ===== STEP 3: DETERMINE DIRECTION (AI-BASED) =====
        signal = "WAIT"
        
        # Logic: AI Trend + Score phải CÙNG CHIỀU
        trend_upper = ai_trend.upper()
        
        if ("BULLISH" in trend_upper) and (ai_score > 0):
            signal = "BUY"
            logger.info("✅ AI Signal: BULLISH + Positive Score → BUY")
        elif ("BEARISH" in trend_upper) and (ai_score < 0):
            signal = "SELL"
            logger.info("✅ AI Signal: BEARISH + Negative Score → SELL")
        else:
            logger.info(f"⏸️ AI Signal: {ai_trend} (Score: {ai_score}) → WAIT (Không rõ ràng)")
            return "WAIT_WEAK_SIGNAL"
        
        # ===== STEP 3.1: SMART ENTRY CHECK - NEW =====
        # Nếu giá đã chạy quá xa điểm Entry của AI (> 3 giá) -> Bỏ qua
        ai_entry = latest_report.get('entry_price', 0.0)
        if ai_entry and ai_entry > 0:
            diff = abs(current_price - ai_entry)
            if diff > 3.0: # 30 pips USD
                 logger.warning(f"⚠️ Price moved too far from AI Entry (Diff > 3). Current: {current_price:.2f}, AI: {ai_entry}. Skip.")
                 return "WAIT_BAD_PRICE"
            else:
                 logger.info(f"✅ Price within valid range (Diff={diff:.2f} <= 3.0).")
        
        # ===== STEP 4: VOLUME CONFIRMATION =====
        try:
            if len(df) >= 20:
                vol_sma20 = df['Volume'].tail(20).mean()
                current_vol = df['Volume'].iloc[-1]
                prev_vol = df['Volume'].iloc[-2]
                
                # Confirmation: Volume hiện tại hoặc nến trước > TB20
                volume_confirmed = (current_vol > vol_sma20) or (prev_vol > vol_sma20)
                
                logger.info(f"📊 Volume: Current={int(current_vol):,}, Prev={int(prev_vol):,}, SMA20={int(vol_sma20):,}")
                
                if not volume_confirmed:
                    logger.warning("⚠️ Volume thấp hơn TB20 → Tín hiệu yếu, bỏ qua lệnh.")
                    return "WAIT_LOW_VOLUME"
                else:
                    logger.info("✅ Volume Confirmed: Có dòng tiền vào")
            else:
                logger.warning("⚠️ Không đủ dữ liệu để tính Volume (< 20 nến). Bỏ qua điều kiện Volume.")
        except Exception as e:
            logger.error(f"❌ Lỗi tính Volume: {e}. Bỏ qua điều kiện Volume.")
        
        # ===== STEP 5: DETERMINE SL/TP (AI Priority -> Fibo Fallback) =====
        
        # 5.1 Check AI Signals
        ai_sl = latest_report.get('stop_loss', 0.0)
        ai_tp = latest_report.get('take_profit', 0.0)
        
        # Log AI Signal details
        if ai_sl > 0 and ai_tp > 0:
            logger.info(f"🧠 AI Explicit Signal Found: Entry={ai_entry}, SL={ai_sl}, TP={ai_tp}")
        
        # 5.2 Calculate Fibonacci (Always calc for reference or fallback)
        fibo = calculate_fibonacci_levels(df)
        support = 0.0
        resistance = float('inf')
        
        if fibo:
            for price in fibo.values():
                if price < current_price and price > support: support = price
                if price > current_price and price < resistance: resistance = price
        
        # 5.3 Set SL/TP
        sl = 0.0
        tp = 0.0
        
        # Logic: If AI SL/TP is valid -> Use AI. Else -> Use Fibo/Fallback.
        if (ai_sl > 0 and ai_tp > 0):
            sl = ai_sl
            tp = ai_tp
            logger.info(f"✅ Using AI-Defined Levels: SL={sl}, TP={tp}")
        else:
            logger.info("ℹ️ AI did not provide explicit SL/TP. Using Fibonacci/Fallback.")
            
            # Fallback Risk Management
            FALLBACK_SL_PIPS = 5.0
            FALLBACK_TP_PIPS = 10.0
            
            if signal == "BUY":
                if support > 0: sl = support
                else: sl = current_price - FALLBACK_SL_PIPS
                
                if resistance != float('inf'): tp = resistance
                else: tp = current_price + FALLBACK_TP_PIPS
                    
            elif signal == "SELL":
                if resistance != float('inf'): sl = resistance
                else: sl = current_price + FALLBACK_SL_PIPS
                
                if support > 0: tp = support
                else: tp = current_price - FALLBACK_TP_PIPS
        
        logger.info(f"🎯 Final Order Params: Signal={signal}, SL={sl:.2f}, TP={tp:.2f} (Current: {current_price:.2f})")
        
        # ===== STEP 6: EXECUTE ORDER =====
        if signal in ["BUY", "SELL"]:
            logger.info(f"🚀 AI Signal: {trend_upper} (Score: {ai_score}) | Decision: {signal}")
            logger.info(f"🚀 Executing {signal} order...")
            
            response = self.client.execute_order(self.symbol, signal, self.volume, sl, tp)
            logger.info(f"📝 MT5 Response: {response}")
            return response
        else:
            logger.info("⏸️ No valid signal (Conditions not met).")
            return "WAIT"

if __name__ == "__main__":
    # Test Run
    logging.basicConfig(level=logging.INFO)
    trader = AutoTrader("XAUUSD", 0.01)
    trader.analyze_and_trade()
