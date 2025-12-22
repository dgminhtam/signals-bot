import pandas as pd
import numpy as np
from typing import Dict, Optional
from app.core import config

logger = config.logger

def calculate_fibonacci_levels(df: pd.DataFrame, window: int = 120) -> Dict[str, float]:
    """
    Tính toán các mức Fibonacci Retracement (CPU Bound).
    """
    try:
        # Lấy window nến gần nhất
        recent_df = df.tail(window)
        
        # Tìm đỉnh và đáy
        price_high = recent_df['High'].max()
        price_low = recent_df['Low'].min()
        diff = price_high - price_low
        
        # Tính các mức Fibonacci (từ đỉnh xuống đáy)
        fibo_levels = {
            '0.0': price_high,
            '0.236': price_high - (diff * 0.236),
            '0.382': price_high - (diff * 0.382),
            '0.5': price_high - (diff * 0.5),
            '0.618': price_high - (diff * 0.618),  # Golden Ratio
            '0.786': price_high - (diff * 0.786),
            '1.0': price_low
        }
        
        return fibo_levels
        
    except Exception as e:
        logger.error(f"❌ Lỗi tính Fibonacci: {e}")
        return {}


def analyze_trend(df: pd.DataFrame, ai_trend: str = None) -> str:
    """
    Xác định xu hướng.
    Ưu tiên AI Trend (nếu có). Fallback về SMA20.
    Returns: "UP" | "DOWN" | "NEUTRAL"
    """
    # 1. AI Override
    if ai_trend:
        t_upper = ai_trend.upper()
        if "BULLISH" in t_upper: return "UP"
        if "BEARISH" in t_upper: return "DOWN"
        return "NEUTRAL"

    # 2. Technical Fallback (SMA20)
    try:
        if len(df) < 20:
             return "UP" if df['Close'].iloc[-1] >= df['Close'].iloc[-2] else "DOWN"
        
        sma20 = df['Close'].tail(20).mean()
        current_price = df['Close'].iloc[-1]
        
        return "UP" if current_price >= sma20 else "DOWN"
    except:
        return "NEUTRAL"

def get_technical_analysis(df: pd.DataFrame) -> str:
    """
    Phân tích kỹ thuật đơn giản (Sync)
    """
    try:
        if df is None or df.empty:
            return "Không có dữ liệu để phân tích."
        
        current_price = df['Close'].iloc[-1]
        fibo_levels = calculate_fibonacci_levels(df, window=120)
        
        support_level = None
        resistance_level = None
        support_name = ""
        resistance_name = ""
        
        if fibo_levels:
            for level_name, price in fibo_levels.items():
                if price < current_price:
                    if support_level is None or price > support_level:
                        support_level = price
                        support_name = level_name
                elif price > current_price:
                    if resistance_level is None or price < resistance_level:
                        resistance_level = price
                        resistance_name = level_name
        
        current_vol = df['Volume'].iloc[-1]
        prev_vol = df['Volume'].iloc[-2] if len(df) > 1 else current_vol
        vol_avg_20 = df['Volume'].tail(20).mean()
        vol_signal = "TĂNG" if current_vol >= prev_vol else "GIẢM"
        
        def fmt_fibo(name):
            try: return f"{float(name)*100:g}"
            except: return name

        support_str = f"{support_level:.2f} (Fibo {fmt_fibo(support_name)})" if support_level else "N/A"
        resistance_str = f"{resistance_level:.2f} (Fibo {fmt_fibo(resistance_name)})" if resistance_level else "N/A"
        
        summary = f"""
- Giá hiện tại: {current_price:.2f}
- Hỗ trợ: {support_str}
- Kháng cự: {resistance_str}
- Volume: {int(current_vol):,} ({vol_signal} vs {int(prev_vol):,})
- Vol TB 20: {int(vol_avg_20):,}
        """
        return summary.strip()
        
    except Exception as e:
        logger.error(f"❌ Lỗi get_technical_analysis: {e}")
        return "Lỗi tính toán."
