# charter.py
import matplotlib
matplotlib.use('Agg') # Backend không giao diện
import matplotlib.pyplot as plt
import mplfinance as mpf
import yfinance as yf
import pandas as pd
import numpy as np
import os
from typing import Tuple, Dict, Optional
from app.core import config # Updated import

logger = config.logger
IMAGES_DIR = config.IMAGES_DIR

# Tạo thư mục chứa ảnh nếu chưa có
if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)

def calculate_fibonacci_levels(df: pd.DataFrame) -> Tuple[Dict[str, float], str]:
    """
    Tính toán các mức Fibonacci dựa trên Swing High/Low trong khung thời gian
    """
    try:
        # Tìm đỉnh và đáy trong dữ liệu hiện tại
        max_price = df['High'].max()
        min_price = df['Low'].min()
        
        # Tìm vị trí (index) của đỉnh và đáy để xác định xu hướng
        id_max = df['High'].idxmax()
        id_min = df['Low'].idxmin()
        
        diff = max_price - min_price
        levels = {}
        trend = "SIDEWAY"

        # Logic xác định xu hướng để vẽ Fibo
        if id_max > id_min: 
            # Đáy trước -> Đỉnh sau => UPTREND (Kéo Fibo từ Đáy lên Đỉnh)
            trend = "UPTREND"
            levels = {
                '0.0': max_price,          # Swing High
                '0.236': max_price - 0.236 * diff,
                '0.382': max_price - 0.382 * diff,
                '0.5': max_price - 0.5 * diff,
                '0.618': max_price - 0.618 * diff,
                '0.786': max_price - 0.786 * diff,
                '1.0': min_price           # Swing Low
            }
        else:
            # Đỉnh trước -> Đáy sau => DOWNTREND (Kéo Fibo từ Đỉnh xuống Đáy)
            trend = "DOWNTREND"
            levels = {
                '0.0': min_price,          # Swing Low
                '0.236': min_price + 0.236 * diff,
                '0.382': min_price + 0.382 * diff,
                '0.5': min_price + 0.5 * diff,
                '0.618': min_price + 0.618 * diff,
                '0.786': min_price + 0.786 * diff,
                '1.0': max_price           # Swing High
            }
            
        return levels, trend
    except Exception as e:
        logger.error(f"Lỗi tính Fibonacci: {e}")
        return {}, "ERROR"

def draw_price_chart(symbol: str = "GC=F") -> Optional[str]:
    logger.info(f"📈 Đang vẽ biểu đồ H1 (Fibonacci) cho {symbol}...")
    try:
        # 1. Lấy dữ liệu H1 trong 5 ngày (1 tuần giao dịch)
        df = yf.download(symbol, period="5d", interval="1h", progress=False, auto_adjust=True)
        
        if df.empty:
            logger.warning("❌ Không lấy được dữ liệu thị trường.")
            return None

        # Fix lỗi MultiIndex và Timezone
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
        df.index = df.index.tz_convert('Asia/Ho_Chi_Minh')
        
        cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        df = df[[c for c in cols if c in df.columns]].astype(float)
        
        # 2. TÍNH TOÁN FIBONACCI
        fibo_levels, trend = calculate_fibonacci_levels(df)
        if not fibo_levels:
            return None
        
        # 3. CẤU HÌNH STYLE
        mc = mpf.make_marketcolors(up='#089981', down='#f23645', edge='inherit', wick='inherit', volume='in')
        s  = mpf.make_mpf_style(base_mpf_style='nightclouds', marketcolors=mc)
        
        filename = f"{IMAGES_DIR}/chart_price.png"

        # Chuẩn bị các đường kẻ ngang (Horizontal Lines) cho Fibo
        hlines_vals = [fibo_levels['0.0'], fibo_levels['0.382'], fibo_levels['0.5'], fibo_levels['0.618'], fibo_levels['1.0']]
        hlines_colors = ['white', 'orange', 'yellow', 'gold', 'white'] 
        hlines_styles = ['-', '--', '-.', '-', '-']

        # 4. VẼ BIỂU ĐỒ
        fig, axlist = mpf.plot(df, type='candle', style=s, 
                 mav=(20, 50), # EMA 20/50 phổ biến trên H1
                 volume=True, 
                 hlines=dict(hlines=hlines_vals, colors=hlines_colors, linestyle=hlines_styles, linewidths=1, alpha=0.7),
                 title=f"\nGOLD H1 Analysis - {trend} (Fibonacci)",
                 ylabel='Price ($)',
                 datetime_format='%d/%m %Hh',
                 figsize=(12, 7), 
                 returnfig=True,
                 savefig=filename
                 )

        # 5. ANNOTATION (GHI CHÚ MỨC FIBO)
        ax = axlist[0]
        
        # Hàm vẽ text bên phải trục
        def add_fibo_label(level_name, price, color):
            ax.text(1.01, price, f'{level_name} ({price:.1f})', 
                    transform=ax.get_yaxis_transform(), 
                    color=color, fontsize=8, fontweight='bold', va='center')

        # Gắn nhãn
        add_fibo_label("Swing High/Low", fibo_levels['0.0'], 'white')
        add_fibo_label("Fibo 0.382", fibo_levels['0.382'], 'orange')
        add_fibo_label("Fibo 0.5", fibo_levels['0.5'], 'yellow')
        add_fibo_label("GOLDEN 0.618", fibo_levels['0.618'], '#00ff00') 
        add_fibo_label("Swing Low/High", fibo_levels['1.0'], 'white')

        # Lưu file
        fig.savefig(filename, bbox_inches='tight') 
        plt.close(fig)
        
        logger.info(f"✅ Đã lưu chart Fibo H1 tại: {filename}")
        return filename

    except Exception as e:
        logger.error(f"❌ Lỗi vẽ chart: {e}")
        return None

def get_technical_analysis(symbol: str = "GC=F") -> str:
    """
    Lấy dữ liệu kỹ thuật tóm tắt để gửi cho AI Engine.
    Returns: String mô tả RSI, Trend, Fibo Levels.
    """
    try:
        # Lấy dữ liệu H1 trong 2 ngày
        df = yf.download(symbol, period="2d", interval="1h", progress=False, auto_adjust=True)
        
        if df.empty: return "Không lấy được dữ liệu kỹ thuật."
        
        # Fix MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        current_price = df['Close'].iloc[-1]
        
        # 1. Tính RSI (14)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        # RSI đánh giá
        rsi_status = "Trung tính"
        if current_rsi > 70: rsi_status = "QUÁ MUA (Overbought) - Cẩn thận đảo chiều giảm"
        elif current_rsi < 30: rsi_status = "QUÁ BÁN (Oversold) - Cẩn thận đảo chiều tăng"
        
        # 2. Tính Trend (theo EMA 20)
        ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        trend_status = "TĂNG (Giá trên EMA20)" if current_price > ema20 else "GIẢM (Giá dưới EMA20)"
        
        # 3. Fibo Levels (Sử dụng hàm có sẵn)
        fibo_levels, trend_fibo = calculate_fibonacci_levels(df)
        
        # Tìm mức Fibo gần nhất
        closest_level = "N/A"
        min_dist = float('inf')
        for name, price in fibo_levels.items():
            dist = abs(current_price - price)
            if dist < min_dist:
                min_dist = dist
                closest_level = f"{name} ({price:.1f})"

        # Tổng hợp text
        summary = f"""
        - Giá hiện tại: {current_price:.1f}
        - Xu hướng H1: {trend_status} | Trend Fibo: {trend_fibo}
        - RSI (14): {current_rsi:.1f} ({rsi_status})
        - Hỗ trợ/Kháng cự gần nhất (Fibo): {closest_level}
        """
        return summary
        
    except Exception as e:
        logger.error(f"❌ Lỗi lấy data kỹ thuật: {e}")
        return "Lỗi tính toán dữ liệu kỹ thuật."

if __name__ == "__main__":
    draw_price_chart()
    print(get_technical_analysis())
