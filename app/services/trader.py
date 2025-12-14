
import logging
from app.services.charter import get_market_data, get_technical_analysis, _analyze_trend
from app.services.mt5_bridge import MT5DataClient

logger = logging.getLogger(__name__)

class AutoTrader:
    def __init__(self, symbol="XAUUSD", volume=0.01):
        self.symbol = symbol
        self.volume = volume
        self.client = MT5DataClient()
        
    def analyze_and_trade(self):
        """
        Quy trình: 
        1. Lấy dữ liệu 
        2. Phân tích (Trend, Fibo) 
        3. Ra quyết định 
        4. Vào lệnh (nếu thỏa mãn)
        """
        logger.info(f"🤖 Starting Analysis for {self.symbol}...")
        
        # 1. Get Data
        df, source = get_market_data(self.symbol)
        if df is None or df.empty:
            logger.error("❌ No data received.")
            return "FAIL_NO_DATA"
            
        # 2. Analyze Trend
        trend = _analyze_trend(df) # "UP", "DOWN", "NEUTRAL"
        
        # 3. Analyze Fibo Levels for SL/TP
        from app.services.charter import calculate_fibonacci_levels
        fibo = calculate_fibonacci_levels(df)
        
        current_price = df['Close'].iloc[-1]
        
        # 4. Trading Logic (Simple Trend Following)
        # Rule: 
        # - BUY if Trend UP. SL = Fibo Support (nearest). TP = Fibo Resistance (next).
        # - SELL if Trend DOWN. SL = Fibo Resistance (nearest). TP = Fibo Support (next).
        
        signal = "WAIT"
        sl = 0.0
        tp = 0.0
        
        # Find nearest Support/Resistance from Fibo
        # (Simplified logic from charter.py)
        support = 0.0
        resistance = float('inf')
        
        for price in fibo.values():
            if price < current_price and price > support:
                support = price
            if price > current_price and price < resistance:
                resistance = price
                
        if trend == "UP":
            signal = "BUY"
            sl = support if support > 0 else current_price - 10.0 # Fallback
            tp = resistance if resistance != float('inf') else current_price + 10.0
            
            # Risk Management Check
            if current_price - sl > (tp - current_price) * 2: 
                # Nếu R:R quá xấu (SL xa hơn TP x2), bỏ qua ?? 
                # (For simplicity, user didn't specify, so we just log)
                logger.warning("⚠️ Risk/Reward unfavortable, but proceeding per simple logic.")

        elif trend == "DOWN":
            signal = "SELL"
            sl = resistance if resistance != float('inf') else current_price + 10.0
            tp = support if support > 0 else current_price - 10.0

        logger.info(f"🧠 Analysis Results: Trend={trend}, Price={current_price:.2f}")
        logger.info(f"🎯 Signal: {signal} | SL: {sl:.2f} | TP: {tp:.2f}")
        
        if signal in ["BUY", "SELL"]:
            # 5. Execute
            logger.info(f"🚀 Executing {signal} order...")
            response = self.client.execute_order(self.symbol, signal, self.volume, sl, tp)
            logger.info(f"📝 MT5 Response: {response}")
            return response
        else:
            logger.info("⏸️ No valid signal (Trend NEUTRAL).")
            return "WAIT"

if __name__ == "__main__":
    # Test Run
    logging.basicConfig(level=logging.INFO)
    trader = AutoTrader("XAUUSD", 0.01)
    trader.analyze_and_trade()
