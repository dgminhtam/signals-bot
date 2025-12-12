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

from app.services.mt5_bridge import MT5DataClient
from app.core import config

logger = config.logger
IMAGES_DIR = config.IMAGES_DIR

if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)

def get_data_from_tradingview(symbol: str = "XAUUSD", exchange: str = "OANDA") -> Optional[pd.DataFrame]:
    """Fallback 1: Lấy dữ liệu từ TradingView"""
    try:
        from app.services.tvdatafeed_client import TvDatafeed, Interval
        
        logger.info(f"🔄 Fallback 1: Đang lấy dữ liệu từ TradingView ({symbol}/{exchange})...")
        tv = TvDatafeed()
        df = tv.get_hist(
            symbol=symbol,
            exchange=exchange,
            interval=Interval.in_1_hour,
            n_bars=80
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
        
        df = df.tail(80)
        logger.info(f"✅ Đã lấy {len(df)} nến từ TradingView.")
        return df
        
    except ImportError:
        logger.warning("⚠️ Chưa cài tvDatafeed, bỏ qua TradingView fallback.")
        return None
    except Exception as e:
        logger.error(f"❌ Lỗi lấy dữ liệu từ TradingView: {e}")
        return None

def get_data_from_yfinance(symbol: str = "XAUUSD", period: str = "5d", interval: str = "1h") -> Optional[pd.DataFrame]:
    """Fallback 2: Lấy dữ liệu từ yfinance nếu cả MT5 và TradingView đều chết"""
    try:
        # Map symbol: XAUUSD -> GC=F (Gold Futures)
        yf_symbol = "GC=F" if symbol == "XAUUSD" else symbol
        
        logger.info(f"🔄 Fallback 2: Đang lấy dữ liệu từ yfinance ({yf_symbol})...")
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
        
        # Lấy 80 nến gần nhất
        df = df.tail(80)
        
        logger.info(f"✅ Đã lấy {len(df)} nến từ yfinance.")
        return df
        
    except Exception as e:
        logger.error(f"❌ Lỗi lấy dữ liệu từ yfinance: {e}")
        return None

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tính toán các chỉ báo kỹ thuật sử dụng pandas
    Áp dụng thống nhất cho tất cả các nguồn dữ liệu
    """
    try:
        # 1. EMA (Exponential Moving Average) - Sử dụng pandas .ewm()
        df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # 2. Support & Resistance (Pivot Points Classic)
        # Pivot = (High + Low + Close) / 3
        # Support1 = (2 * Pivot) - High
        # Resistance1 = (2 * Pivot) - Low
        
        pivot = (df['High'] + df['Low'] + df['Close']) / 3
        df['Support'] = (2 * pivot) - df['High']
        df['Resistance'] = (2 * pivot) - df['Low']
        
        # 3. Smooth S/R bằng moving average để tránh nhiễu
        df['Support'] = df['Support'].rolling(window=3, min_periods=1).mean()
        df['Resistance'] = df['Resistance'].rolling(window=3, min_periods=1).mean()
        
        # 4. Forward fill NaN values (do EMA cần data đủ dài)
        df['EMA50'] = df['EMA50'].ffill().bfill()
        df['EMA200'] = df['EMA200'].ffill().bfill()
        df['Support'] = df['Support'].ffill().bfill()
        df['Resistance'] = df['Resistance'].ffill().bfill()
        
        logger.info("✅ Đã tính toán indicators (EMA, S/R) bằng pandas.")
        return df
        
    except Exception as e:
        logger.error(f"❌ Lỗi tính toán indicators: {e}")
        return df

def draw_price_chart(symbol: str = "XAUUSD") -> Optional[str]:
    logger.info(f"📈 Đang vẽ biểu đồ H1 (Pro Dark Style) cho {symbol}...")
    
    data_source = "Unknown"
    try:
        # 1. Thử TradingView trước (Primary - nhanh và ổn định)
        df = None
        df = get_data_from_tradingview(symbol)
        if df is not None and not df.empty:
            data_source = "TradingView"
        
        # 2. Fallback 1: MT5 (Real-time với Indicators)
        if df is None or df.empty:
            logger.warning("⚠️ TradingView không khả dụng, chuyển sang MT5...")
            client = MT5DataClient()
            if client.connect():
                df = client.get_historical_data(symbol, timeframe="H1", count=80)
                client.disconnect()
                
                if df is not None and not df.empty:
                    data_source = "MT5"
                    logger.info(f"✅ Đã lấy {len(df)} nến từ MT5.")
        
        # 3. Fallback 2: yfinance (Last resort)
        if df is None or df.empty:
            logger.warning("⚠️ MT5 không khả dụng, chuyển sang yfinance...")
            df = get_data_from_yfinance(symbol)
            if df is not None and not df.empty:
                data_source = "yfinance"
            
        if df is None or df.empty:
            logger.error("❌ Không thể lấy dữ liệu từ cả 3 nguồn (TradingView, MT5, yfinance).")
            return None
        
        # 4. Tính toán indicators thống nhất bằng pandas-ta
        df = calculate_indicators(df)

        # 2. CẤU HÌNH STYLE CHUYÊN NGHIỆP (PRO DARK)
        # Màu sắc chuẩn
        up_color = '#089981'    # Xanh Binance/TradingView
        down_color = '#f23645'  # Đỏ Binance/TradingView
        bg_color = '#131722'    # Màu nền tối TradingView
        grid_color = '#2a2e39'  # Màu lưới rất mờ
        text_color = '#d1d4dc'  # Màu chữ sáng

        # Cấu hình màu nến (quan trọng để nến trông gọn)
        mc = mpf.make_marketcolors(
            up=up_color, down=down_color,
            edge='inherit',  # Viền cùng màu thân nến -> trông gọn hơn
            wick='inherit',  # Râu cùng màu thân nến
            volume='in'
        )

        # Cấu hình style tổng thể Custom
        s = mpf.make_mpf_style(
            marketcolors=mc,
            gridstyle=':',          # Lưới chấm bị
            gridcolor=grid_color,   # Màu lưới mờ
            gridaxis='both',        # Hiện lưới cả 2 trục
            y_on_right=True,        # Trục giá bên phải
            facecolor=bg_color,     # Màu nền vùng vẽ biểu đồ
            figcolor=bg_color,      # Màu nền viền ngoài
            # Tùy chỉnh sâu hơn vào Matplotlib (rc params) để làm sạch giao diện
            rc={
                'font.family': 'monospace', # Dùng font Monospace cho "vuông vức"
                'font.monospace': ['Consolas', 'DejaVu Sans Mono', 'Liberation Mono', 'Courier New'],
                'axes.labelcolor': text_color,
                'xtick.color': text_color,
                'ytick.color': text_color,
                'axes.spines.bottom': True,  # Hien border duoi
                'axes.spines.top': True,     # Hien border tren
                'axes.spines.left': True,    # Hien border trai
                'axes.spines.right': True,   # Hien border phai
                'axes.linewidth': 0.8,       # Do day border manh
                'axes.edgecolor': '#FFFFFF'  # Trắng xám không quá nổi (Subtle Gray)
            }
        )
        
        filename = f"{IMAGES_DIR}/chart_price.png"

        # 2b. TẠO ADDPLOTS (INDICATORS)
        add_plots = []
        
        # Check EMA50 & EMA200 logic
        if 'EMA50' in df.columns and 'EMA200' in df.columns:
            # Lấy data, fillna để tránh lỗi plot
            ema50 = df['EMA50'].bfill()
            ema200 = df['EMA200'].bfill()
            
            # EMA 50 - Mau Cyan/Blue
            add_plots.append(mpf.make_addplot(ema50, color='#2962FF', width=0.8))
            # EMA 200 - Mau Orange
            add_plots.append(mpf.make_addplot(ema200, color='#FF6D00', width=1.0))

        # Check Support & Resistance logic
        if 'Support' in df.columns and 'Resistance' in df.columns:
            # Dùng scatter hoặc line. Ở đây dùng line đứt đoạn cho chuyên nghiệp
            sup = df['Support']
            res = df['Resistance']
            
            # Support: Green, Dashed
            add_plots.append(mpf.make_addplot(sup, color='#00E676', width=1.0, linestyle='--'))
            # Resistance: Red, Dashed
            add_plots.append(mpf.make_addplot(res, color='#FF1744', width=1.0, linestyle='--'))

        # 3. VẼ BIỂU ĐỒ
        fig, axlist = mpf.plot(
            df, 
            type='candle', 
            style=s, 
            volume=False,
            addplot=add_plots, # <--- ACTIVE EMA
            # Tiêu đề đơn giản, màu trắng
            title="", # Disable default title to use custom text
            ylabel='', 
            datetime_format='%d/%m %H:%M',
            xrotation=0, 
            figsize=(14, 8), 
            tight_layout=True,
            returnfig=True,
            savefig=filename
        )

        # 4. TẠO THẺ GIÁ HIỆN TẠI (PRICE TAG)
        ax = axlist[0]
        
        # 4.1 CUSTOM TITLE (Top-Left)
        # Line 1: Symbol - Timeframe
        ax.text(0.02, 0.96, f"{symbol} - H1", transform=ax.transAxes, 
                color=text_color, fontsize=12, fontweight='bold', va='top')
        # Line 2: Full Name + Data Source
        ax.text(0.02, 0.91, f"Gold US Dollar ({data_source})", transform=ax.transAxes,
                color=text_color, fontsize=10, alpha=0.6, va='top')
        
        # Line 3: Legend (Indicators)
        if 'EMA50' in df.columns:
            ax.text(0.02, 0.86, "EMA 50", transform=ax.transAxes, 
                    color='#2962FF', fontsize=9, fontweight='bold', va='top')
            ax.text(0.08, 0.86, "EMA 200", transform=ax.transAxes, 
                    color='#FF6D00', fontsize=9, fontweight='bold', va='top')
        
        if 'Support' in df.columns:
             ax.text(0.14, 0.86, "Support", transform=ax.transAxes, 
                    color='#00E676', fontsize=9, fontweight='bold', va='top')
             ax.text(0.20, 0.86, "Resistance", transform=ax.transAxes, 
                    color='#FF1744', fontsize=9, fontweight='bold', va='top')
        last_row = df.iloc[-1]
        current_price = last_row['Close']
        
        # Xác định màu tag theo nến hiện tại
        tag_color = up_color if current_price >= last_row['Open'] else down_color
        
        # Đường kẻ ngang mờ
        ax.axhline(y=current_price, color=tag_color, linestyle='--', linewidth=0.8, alpha=0.7)

        # Hộp giá (Badge)
        ax.text(
            1.002, current_price, 
            f' {current_price:.2f} ',
            transform=ax.get_yaxis_transform(),
            color='white', 
            fontsize=10, 
            fontweight='normal', 
            va='center', ha='left',
            bbox=dict(
                boxstyle="square,pad=0.3", 
                facecolor=tag_color, 
                edgecolor=tag_color, 
                alpha=1.0
            )
        )

        # 5. Lưu ảnh (High Quality)
        fig.savefig(filename, bbox_inches='tight', pad_inches=0.1, dpi=300, facecolor=fig.get_facecolor())
        plt.close(fig)
        
        logger.info(f"✅ Đã lưu chart Pro Style tại: {filename}")
        return filename

    except Exception as e:
        logger.error(f"❌ Lỗi vẽ chart: {e}")
        return None

# Hàm get_technical_analysis giữ nguyên không đổi
def get_technical_analysis(symbol: str = "XAUUSD") -> str:
    try:
        client = MT5DataClient()
        if not client.connect(): return "Lỗi kết nối MT5."
        df = client.get_historical_data(symbol, timeframe="H1", count=100)
        client.disconnect()
        if df is None or df.empty: return "Không lấy được dữ liệu."
        current_price = df['Close'].iloc[-1]
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        rsi_status = "Trung tính"
        if current_rsi > 70: rsi_status = "QUÁ MUA (Overbought)"
        elif current_rsi < 30: rsi_status = "QUÁ BÁN (Oversold)"
        ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        trend_status = "TĂNG" if current_price > ema20 else "GIẢM"
        highest_price = df['High'].max()
        lowest_price = df['Low'].min()
        dist_to_high = abs(highest_price - current_price)
        dist_to_low = abs(lowest_price - current_price)
        nearest_level = f"Kháng cự {highest_price:.2f}" if dist_to_high < dist_to_low else f"Hỗ trợ {lowest_price:.2f}"
        summary = f"""
        - Giá hiện tại: {current_price:.2f}
        - Xu hướng H1: {trend_status} (EMA20)
        - RSI (14): {current_rsi:.1f} ({rsi_status})
        - Cản gần nhất: {nearest_level}
        """
        return summary
    except Exception as e:
        logger.error(f"❌ Lỗi data kỹ thuật: {e}")
        return "Lỗi tính toán."

def draw_tv_chart(symbol: str = "XAUUSD", exchange: str = "OANDA") -> Optional[str]:
    """
    Vẽ biểu đồ đơn giản từ TradingView datafeed (Không có indicator)
    Lưu vào: tv_chart_price.png
    """
    logger.info(f"📺 Đang vẽ biểu đồ TradingView cho {symbol}...")
    
    try:
        from app.services.tvdatafeed_client import TvDatafeed, Interval
        
        # 1. Khởi tạo TvDatafeed (No login - public data)
        tv = TvDatafeed()
        
        # 2. Lấy dữ liệu (80 nến H1)
        logger.info(f"📡 Đang lấy dữ liệu từ TradingView ({symbol}/{exchange})...")
        df = tv.get_hist(
            symbol=symbol,
            exchange=exchange,
            interval=Interval.in_1_hour,
            n_bars=80
        )
        
        if df is None or df.empty:
            logger.error("❌ TradingView không trả về dữ liệu.")
            return None
        
        # 3. Chuẩn hóa DataFrame cho mplfinance
        # TvDatafeed trả về: datetime, symbol, open, high, low, close, volume
        df.index.name = 'Date'
        df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }, inplace=True)
        
        logger.info(f"✅ Đã lấy {len(df)} nến từ TradingView.")
        
        # 4. Style đơn giản (Dark, Clean)
        up_color = '#089981'
        down_color = '#f23645'
        bg_color = '#131722'
        grid_color = '#2a2e39'
        text_color = '#d1d4dc'
        
        mc = mpf.make_marketcolors(
            up=up_color, down=down_color,
            edge='inherit',
            wick='inherit',
            volume='in'
        )
        
        s = mpf.make_mpf_style(
            marketcolors=mc,
            gridstyle=':',
            gridcolor=grid_color,
            gridaxis='both',
            y_on_right=True,
            facecolor=bg_color,
            figcolor=bg_color,
            rc={
                'font.family': 'monospace',
                'font.monospace': ['Consolas', 'DejaVu Sans Mono', 'Liberation Mono', 'Courier New'],
                'axes.labelcolor': text_color,
                'xtick.color': text_color,
                'ytick.color': text_color,
                'axes.spines.bottom': True,
                'axes.spines.top': True,
                'axes.spines.left': True,
                'axes.spines.right': True,
                'axes.linewidth': 0.8,
                'axes.edgecolor': '#FFFFFF'
            }
        )
        
        filename = f"{IMAGES_DIR}/tv_chart_price.png"
        
        # 5. Vẽ biểu đồ (Simple, No Indicators)
        fig, axlist = mpf.plot(
            df,
            type='candle',
            style=s,
            volume=False,
            title="",
            ylabel='',
            datetime_format='%d/%m %H:%M',
            xrotation=0,
            figsize=(14, 8),
            tight_layout=True,
            returnfig=True,
            savefig=filename
        )
        
        # 6. Custom Header
        ax = axlist[0]
        ax.text(0.02, 0.96, f"{symbol} - H1 (TradingView)", transform=ax.transAxes,
                color=text_color, fontsize=12, fontweight='bold', va='top')
        ax.text(0.02, 0.91, "Gold US Dollar", transform=ax.transAxes,
                color=text_color, fontsize=10, alpha=0.6, va='top')
        
        # 7. Current Price Tag
        last_row = df.iloc[-1]
        current_price = last_row['Close']
        tag_color = up_color if current_price >= last_row['Open'] else down_color
        
        ax.axhline(y=current_price, color=tag_color, linestyle='--', linewidth=0.8, alpha=0.7)
        ax.text(
            1.002, current_price,
            f' {current_price:.2f} ',
            transform=ax.get_yaxis_transform(),
            color='white',
            fontsize=10,
            fontweight='normal',
            va='center', ha='left',
            bbox=dict(
                boxstyle="square,pad=0.3",
                facecolor=tag_color,
                edgecolor=tag_color,
                alpha=1.0
            )
        )
        
        # 8. Save
        fig.savefig(filename, bbox_inches='tight', pad_inches=0.1, dpi=300, facecolor=fig.get_facecolor())
        plt.close(fig)
        
        logger.info(f"✅ Đã lưu TradingView chart tại: {filename}")
        return filename
        
    except ImportError:
        logger.error("❌ Chưa cài tvDatafeed. Chạy: pip install --upgrade --no-cache-dir git+https://github.com/rongardF/tvdatafeed.git")
        return None
    except Exception as e:
        logger.error(f"❌ Lỗi vẽ TradingView chart: {e}")
        return None

if __name__ == "__main__":
    draw_price_chart()