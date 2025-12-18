# charter.py
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import numpy as np
import yfinance as yf
from typing import Tuple, Dict, Optional
import os
import sys
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Add project root to path to allow direct execution
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

from app.services.mt5_bridge import MT5DataClient
from app.core import config

logger = config.logger
IMAGES_DIR = config.IMAGES_DIR

if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)

# Helper for Sync Libraries
def _sync_get_data_from_tradingview(symbol: str, exchange: str) -> Optional[pd.DataFrame]:
    try:
        from app.services.tvdatafeed_client import TvDatafeed, Interval
        
        logger.info(f"🔄 Fallback 2: Đang lấy dữ liệu từ TradingView ({symbol}/{exchange})...")
        tv = TvDatafeed()
        df = tv.get_hist(
            symbol=symbol,
            exchange=exchange,
            interval=Interval.in_1_hour,
            n_bars=120
        )
        
        if df is None or df.empty:
            logger.warning("⚠️ TradingView không trả về dữ liệu.")
            return None
        
        # Chuẩn hóa cột
        df.index.name = 'Date'
        df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }, inplace=True)
        
        df = df.tail(120)
        logger.info(f"✅ Đã lấy {len(df)} nến từ TradingView.")
        return df
        
    except ImportError:
        logger.warning("⚠️ Chưa cài tvDatafeed, bỏ qua TradingView fallback.")
        return None
    except Exception as e:
        logger.error(f"❌ Lỗi lấy dữ liệu từ TradingView: {e}")
        return None

def _sync_get_data_from_yfinance(symbol: str, period: str, interval: str) -> Optional[pd.DataFrame]:
    try:
        # Map symbol: XAUUSD -> GC=F (Gold Futures)
        yf_symbol = "GC=F" if symbol == "XAUUSD" else symbol
        
        logger.info(f"🔄 Fallback 3: Đang lấy dữ liệu từ yfinance ({yf_symbol})...")
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty:
            logger.warning("⚠️ yfinance không trả về dữ liệu.")
            return None
        
        # Chuẩn hóa cột để khớp với MT5 format
        df.rename(columns={
            'Open': 'Open',
            'High': 'High', 
            'Low': 'Low',
            'Close': 'Close',
            'Volume': 'Volume'
        }, inplace=True)
        
        # Lấy 120 nến gần nhất
        df = df.tail(120)
        
        logger.info(f"✅ Đã lấy {len(df)} nến từ yfinance.")
        return df
        
    except Exception as e:
        logger.error(f"❌ Lỗi lấy dữ liệu từ yfinance: {e}")
        return None

async def get_market_data(symbol: str = "XAUUSD") -> Tuple[Optional[pd.DataFrame], str]:
    """
    Hàm trung tâm để lấy dữ liệu thị trường (Async) theo thứ tự: MT5 -> TradingView -> yfinance
    Trả về (DataFrame, source_name)
    """
    logger.info(f"📊 Đang lấy dữ liệu thị trường cho {symbol}...")
    
    df = None
    loop = asyncio.get_running_loop()
    
    # 1. Thử MT5 trước (Primary - Async Native)
    client = MT5DataClient()
    try:
        if await client.connect():
            logger.info("🔌 Kết nối MT5 thành công, đang lấy dữ liệu...")
            df = await client.get_historical_data(symbol, timeframe="H1", count=120)
            await client.disconnect()
            
            if df is not None and not df.empty:
                logger.info(f"✅ Đã lấy dữ liệu từ MT5")
                return df, "MT5"
        else:
            logger.warning("⚠️ Không thể kết nối MT5.")
    except Exception as e:
        logger.error(f"❌ Lỗi kết nối MT5: {e}")

    # 2. Fallback 1: TradingView (Sync wrapped in Executor)
    logger.warning("⚠️ Chuyển sang TradingView...")
    try:
        df = await loop.run_in_executor(None, _sync_get_data_from_tradingview, symbol, "OANDA")
        if df is not None and not df.empty:
            logger.info(f"✅ Đã lấy dữ liệu từ TradingView")
            return df, "TradingView"
    except Exception as e:
        logger.error(f"❌ Lỗi Fallback TradingView: {e}")
    
    # 3. Fallback 2: yfinance (Sync wrapped in Executor)
    logger.warning("⚠️ TradingView không khả dụng, chuyển sang yfinance...")
    try:
        df = await loop.run_in_executor(None, _sync_get_data_from_yfinance, symbol, "5d", "1h")
        if df is not None and not df.empty:
            logger.info(f"✅ Đã lấy dữ liệu từ yfinance")
            return df, "yfinance"
    except Exception as e:
         logger.error(f"❌ Lỗi Fallback yfinance: {e}")
    
    logger.error("❌ Không thể lấy dữ liệu từ cả 3 nguồn")
    return None, "None"

def calculate_fibonacci_levels(df: pd.DataFrame, window: int = 120) -> Dict[str, float]:
    """
    Tính toán các mức Fibonacci Retracement (CPU Bound - Fast enough to keep sync or await loop if needed)
    Keeping sync for simplicity as logic is lightweight math.
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


def _analyze_trend(df: pd.DataFrame, ai_trend: str = None) -> str:
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

def _prepare_volume_plots(plot_df: pd.DataFrame, up_color: str, down_color: str) -> list:
    """
    Tách logic xử lý indicator volume - trả về list addplot
    """
    try:
        volume_up = plot_df['Volume'].copy()
        volume_down = plot_df['Volume'].copy()
        
        prev_volume = plot_df['Volume'].shift(1)

        for i in range(len(plot_df)):
            current_vol = plot_df['Volume'].iloc[i]
            
            if pd.isna(current_vol):
                volume_up.iloc[i] = np.nan
                volume_down.iloc[i] = np.nan
                continue

            previous_vol = prev_volume.iloc[i]

            if pd.isna(previous_vol):
                volume_down.iloc[i] = np.nan
                continue

            if current_vol >= previous_vol:
                volume_down.iloc[i] = np.nan
            else:
                volume_up.iloc[i] = np.nan
        
        return [
            mpf.make_addplot(volume_up, panel=1, color=up_color, 
                           type='bar', width=0.4, ylabel='Volume', secondary_y=False),
            mpf.make_addplot(volume_down, panel=1, color=down_color, 
                           type='bar', width=0.4, secondary_y=False)
        ]
    except Exception as e:
        logger.error(f"❌ Error preparing volume plots: {e}")
        return []

def draw_price_chart(symbol: str = "XAUUSD", df: Optional[pd.DataFrame] = None, data_source: str = "Unknown", ai_trend: str = None) -> Optional[str]:
    """
    Vẽ biểu đồ giá với Fibonacci levels (SYNC - CPU BOUND).
    Người gọi hàm này nên bọc trong `await asyncio.to_thread` nếu muốn không block.
    """
    logger.info(f"📈 Đang vẽ biểu đồ H1 (Pro Dark Style) cho {symbol}...")
    
    try:
        # Chú ý: Hàm này giả định DF đã được truyền vào từ bên ngoài (đã await xong).
        # Nếu df None, ta không thể gọi await get_market_data() ở đây vì đây là sync func.
        # Chúng ta sẽ trả về None nếu df is None.
        if df is None:
            logger.error("❌ DataFrame is None in draw_price_chart. Cannot fetch data inside sync function.")
            return None
        
        # Ensure data is sorted by Date (Oldest to Newest)
        df.sort_index(inplace=True)
        
        # Decision: Draw Volume only if source is MT5
        draw_volume = (data_source == "MT5")

        # 2. CẤU HÌNH STYLE CHUYÊN NGHIỆP (PRO DARK)
        up_color = '#089981'    
        down_color = '#f23645'  
        bg_color = '#131722'    
        grid_color = '#2a2e39'  
        text_color = '#d1d4dc'  

        mc = mpf.make_marketcolors(
            up=up_color, down=down_color,
            edge='inherit', wick='inherit', volume='in'
        )

        s = mpf.make_mpf_style(
            marketcolors=mc,
            gridstyle=':', gridcolor=grid_color, gridaxis='both',
            y_on_right=True, facecolor=bg_color, figcolor=bg_color,
            rc={
                'font.family': 'monospace',
                'axes.labelcolor': text_color, 'xtick.color': text_color, 'ytick.color': text_color,
                'axes.spines.bottom': True, 'axes.spines.top': True, 'axes.spines.left': True, 'axes.spines.right': True,
                'axes.linewidth': 0.8, 'axes.edgecolor': '#FFFFFF'
            }
        )
        
        filename = f"{IMAGES_DIR}/chart_price.png"

        # Padding
        last_date = df.index[-1]
        padding_candles = 20
        future_dates = pd.date_range(start=last_date + pd.Timedelta(hours=1), periods=padding_candles, freq='h')
        padding_df = pd.DataFrame(index=future_dates, columns=df.columns)
        padding_df[:] = np.nan
        plot_df = pd.concat([df, padding_df])

        # Volume
        apds = []
        if draw_volume:
            apds = _prepare_volume_plots(plot_df, up_color, down_color)
            
        kwargs = dict(
            type='candle', style=s, volume=False, 
            title="", ylabel='', datetime_format='%d/%m %H:%M',
            xrotation=0, figsize=(14, 9), tight_layout=True,
            returnfig=True, savefig=filename,
            update_width_config=dict(candle_width=0.6)
        )
        
        if draw_volume:
            kwargs['addplot'] = apds
            kwargs['panel_ratios'] = (3, 1)
        
        fig, axlist = mpf.plot(plot_df, **kwargs)

        # Volume Panel Fix
        if draw_volume and len(axlist) > 1:
            volume_ax = axlist[2] if len(axlist) >= 3 else axlist[1]
            if volume_ax:
                max_vol = plot_df['Volume'].max()
                if pd.notna(max_vol) and max_vol > 0:
                    volume_ax.set_ylim(0, max_vol * 1.1)

        # Tags & Fibo
        ax = axlist[0]
        ax.text(0.02, 0.96, f"{symbol} - H1", transform=ax.transAxes, color=text_color, fontsize=12, fontweight='bold', va='top')
        ax.text(0.02, 0.91, f"Gold US Dollar ({data_source})", transform=ax.transAxes, color=text_color, fontsize=10, alpha=0.6, va='top')
        
        last_row = df.iloc[-1]
        current_price = last_row['Close']
        tag_color = up_color if current_price >= last_row['Open'] else down_color
        ax.axhline(y=current_price, color=tag_color, linestyle='--', linewidth=0.8, alpha=0.7)
        ax.text(1.002, current_price, f' {current_price:.2f} ', transform=ax.get_yaxis_transform(),
                color='white', fontsize=10, va='center', ha='left',
                bbox=dict(boxstyle="square,pad=0.3", facecolor=tag_color, edgecolor=tag_color, alpha=1.0))

        # Fibonacci
        fibo_levels = calculate_fibonacci_levels(df, window=140)
        if fibo_levels:
            fibo_color = '#1E90FF'
            for level_name, price in fibo_levels.items():
                alpha = 0.9 if level_name == '0.618' else (0.8 if level_name == '0.5' else 0.6)
                linewidth = 0.7 if level_name == '0.618' else 0.6
                
                ax.axhline(y=price, color=fibo_color, linestyle='-', linewidth=linewidth, alpha=alpha, zorder=1)
                
                try: perc_label = f"{float(level_name)*100:g}"
                except: perc_label = level_name

                ax.text(1.002, price, f' Fibo {perc_label}: {price:.2f} ', transform=ax.get_yaxis_transform(),
                        color=fibo_color, fontsize=8, fontweight='bold' if level_name in ['0.618', '0.5'] else 'normal',
                        va='center', ha='left', alpha=alpha,
                        bbox=dict(boxstyle="square,pad=0.2", facecolor=bg_color, edgecolor=fibo_color, alpha=0.7, linewidth=0.5))

        # Trend Arrow
        trend = _analyze_trend(df, ai_trend)
        arrow_color = up_color if trend == "UP" else down_color
        arrow_text = "TĂNG" if trend == "UP" else "GIẢM"
        trend_source = "AI" if ai_trend else "MA20"
        
        ax.annotate(f"Xu hướng ({trend_source}): {arrow_text}", xy=(0.95, 0.92), xycoords='axes fraction',
                    fontsize=12, fontweight='bold', color=arrow_color, ha='right', va='top',
                    bbox=dict(boxstyle="round,pad=0.3", fc=bg_color, ec=arrow_color, alpha=0.8))
        
        arrow_marker = '▲' if trend == "UP" else '▼'
        ax.text(0.96, 0.92, arrow_marker, transform=ax.transAxes, color=arrow_color, fontsize=18, fontweight='bold', ha='left', va='top')

        fig.savefig(filename, bbox_inches='tight', pad_inches=0.1, dpi=300, facecolor=fig.get_facecolor())
        plt.close(fig)
        return filename

    except Exception as e:
        logger.error(f"❌ Lỗi vẽ chart: {e}")
        return None

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

if __name__ == "__main__":
    # Test Async Flow
    async def test_main():
        try:
            df, source = await get_market_data("XAUUSD")
            if df is not None:
                print("--- Technical Analysis ---")
                print(get_technical_analysis(df))
                print("--------------------------")
                
                # Draw Chart (Run in thread pool usually, but detailed test here)
                chart_path = await asyncio.to_thread(draw_price_chart, "XAUUSD", df, source)
                print(f"Chart saved to: {chart_path}")
        except Exception as e:
            logger.error(f"Test Failed: {e}")

    asyncio.run(test_main())
