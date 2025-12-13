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
            n_bars=100
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
        
        df = df.tail(100)
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
        
        # Lấy 100 nến gần nhất
        df = df.tail(100)
        
        logger.info(f"✅ Đã lấy {len(df)} nến từ yfinance.")
        return df
        
    except Exception as e:
        logger.error(f"❌ Lỗi lấy dữ liệu từ yfinance: {e}")
        return None

def get_market_data(symbol: str = "XAUUSD") -> Optional[pd.DataFrame]:
    """
    Hàm trung tâm để lấy dữ liệu thị trường từ TradingView -> MT5 -> yfinance
    Trả về DataFrame hoặc None
    """
    logger.info(f"📊 Đang lấy dữ liệu thị trường cho {symbol}...")
    
    df = None
    
    # 1. Thử TradingView trước (Primary)
    df = get_data_from_tradingview(symbol)
    if df is not None and not df.empty:
        logger.info(f"✅ Đã lấy dữ liệu từ TradingView")
        return df
    
    # 2. Fallback 1: MT5
    logger.warning("⚠️ TradingView không khả dụng, chuyển sang MT5...")
    client = MT5DataClient()
    if client.connect():
        df = client.get_historical_data(symbol, timeframe="H1", count=100)
        client.disconnect()
        if df is not None and not df.empty:
            logger.info(f"✅ Đã lấy dữ liệu từ MT5")
            return df
    
    # 3. Fallback 2: yfinance
    logger.warning("⚠️ MT5 không khả dụng, chuyển sang yfinance...")
    df = get_data_from_yfinance(symbol)
    if df is not None and not df.empty:
        logger.info(f"✅ Đã lấy dữ liệu từ yfinance")
        return df
    
    logger.error("❌ Không thể lấy dữ liệu từ cả 3 nguồn")
    return None

def calculate_fibonacci_levels(df: pd.DataFrame, window: int = 100) -> Dict[str, float]:
    """
    Tính toán các mức Fibonacci Retracement dựa trên window nến gần nhất
    
    Args:
        df: DataFrame chứa dữ liệu OHLC
        window: Số nến sử dụng để tính (mặc định 100)
    
    Returns:
        Dictionary chứa các mức Fibonacci {level_name: price}
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
        
        logger.info(f"✅ Fibonacci levels calculated: High={price_high:.2f}, Low={price_low:.2f}")
        return fibo_levels
        
    except Exception as e:
        logger.error(f"❌ Lỗi tính Fibonacci: {e}")
        return {}


def draw_price_chart(symbol: str = "XAUUSD", df: Optional[pd.DataFrame] = None, data_source: str = "Unknown") -> Optional[str]:
    """
    Vẽ biểu đồ giá với Fibonacci levels
    
    Args:
        symbol: Symbol để vẽ (dùng cho tiêu đề)
        df: DataFrame chứa dữ liệu OHLC (nếu None sẽ tự động lấy)
        data_source: Tên nguồn dữ liệu (để hiển thị)
    """
    logger.info(f"📈 Đang vẽ biểu đồ H1 (Pro Dark Style) cho {symbol}...")
    
    try:
        # Nếu không có DataFrame, tự động lấy dữ liệu
        if df is None:
            df = get_market_data(symbol)
            if df is None or df.empty:
                logger.error("❌ Không thể lấy dữ liệu để vẽ biểu đồ.")
                return None
            data_source = "Auto-fetched"
        
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

        # Padding: Thêm 20 nến ảo vào cuối để tạo khoảng trống
        last_date = df.index[-1]
        padding_candles = 20
        # Tạo DateIndex tiếp theo
        # Assuming H1 frequency, but robust to use Timedelta
        future_dates = pd.date_range(start=last_date + pd.Timedelta(hours=1), periods=padding_candles, freq='h')
        padding_df = pd.DataFrame(index=future_dates, columns=df.columns)
        padding_df[:] = np.nan
        
        # Nối df gốc và padding
        plot_df = pd.concat([df, padding_df])

        # 3. CHUẨN BỊ VOLUME BARS (Xanh/Đỏ)
        # Tách volume thành 2 series: up và down
        volume_up = plot_df['Volume'].copy()
        volume_down = plot_df['Volume'].copy()
        
        for i in range(len(plot_df)):
            if pd.isna(plot_df['Close'].iloc[i]) or pd.isna(plot_df['Open'].iloc[i]):
                volume_up.iloc[i] = np.nan
                volume_down.iloc[i] = np.nan
            elif plot_df['Close'].iloc[i] >= plot_df['Open'].iloc[i]:
                # Nến tăng - chỉ hiện volume_up
                volume_down.iloc[i] = np.nan
            else:
                # Nến giảm - chỉ hiện volume_down
                volume_up.iloc[i] = np.nan
        
        # Tạo 2 addplot riêng cho volume up và down dưới dạng bars
        apds = [
            mpf.make_addplot(volume_up, panel=1, color=up_color, 
                           type='bar', width=0.8, alpha=0.8, ylabel='Volume'),
            mpf.make_addplot(volume_down, panel=1, color=down_color, 
                           type='bar', width=0.8, alpha=0.8)
        ]

        # 3. VẼ BIỂU ĐỒ
        fig, axlist = mpf.plot(
            plot_df, 
            type='candle', 
            style=s, 
            volume=False,  # Tắt volume mặc định
            addplot=apds,  # Thêm volume custom
            panel_ratios=(3, 1),  # Tỷ lệ giữa price panel và volume panel (3:1)
            # Tiêu đề đơn giản, màu trắng
            title="", # Disable default title to use custom text
            ylabel='', 
            datetime_format='%d/%m %H:%M',
            xrotation=0, 
            figsize=(14, 9),  # Tăng chiều cao một chút cho volume panel
            tight_layout=True,
            returnfig=True,
            savefig=filename
        )

        # 4. CẤU HÌNH VOLUME PANEL
        # Set volume y-axis limits
        if len(axlist) > 1:
            volume_ax = axlist[1]
            volume_ax.set_ylim(0, 55100)

        # 4. TẠO THẺ GIÁ HIỆN TẠI (PRICE TAG)
        ax = axlist[0]
        
        # 4.1 CUSTOM TITLE (Top-Left)
        # Line 1: Symbol - Timeframe
        ax.text(0.02, 0.96, f"{symbol} - H1", transform=ax.transAxes, 
                color=text_color, fontsize=12, fontweight='bold', va='top')
        # Line 2: Full Name + Data Source
        ax.text(0.02, 0.91, f"Gold US Dollar ({data_source})", transform=ax.transAxes,
                color=text_color, fontsize=10, alpha=0.6, va='top')
        
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

        # 4.2 VẼ CÁC MỨC FIBONACCI RETRACEMENT
        fibo_levels = calculate_fibonacci_levels(df, window=100)
        
        if fibo_levels:
            fibo_color = '#1E90FF'  # Dodger Blue color
            
            for level_name, price in fibo_levels.items():
                # Xác định độ đậm dựa trên mức quan trọng
                if level_name == '0.618':  # Golden Ratio - quan trọng nhất
                    alpha = 0.9
                    linewidth = 0.7
                elif level_name == '0.5':  # Mức 50% - quan trọng
                    alpha = 0.8
                    linewidth = 0.6
                else:
                    alpha = 0.6
                    linewidth = 0.6
                
                # Vẽ đường ngang Fibonacci
                ax.axhline(y=price, color=fibo_color, linestyle='-', 
                          linewidth=linewidth, alpha=alpha, zorder=1)
                
                # Vẽ nhãn giá bên phải
                ax.text(
                    1.002, price,
                    f' Fibo {level_name}: {price:.2f} ',
                    transform=ax.get_yaxis_transform(),
                    color=fibo_color,
                    fontsize=8,
                    fontweight='bold' if level_name in ['0.618', '0.5'] else 'normal',
                    va='center', ha='left',
                    alpha=alpha,
                    bbox=dict(
                        boxstyle="square,pad=0.2",
                        facecolor=bg_color,
                        edgecolor=fibo_color,
                        alpha=0.7,
                        linewidth=0.5
                    )
                )
            
            logger.info(f"✅ Đã vẽ {len(fibo_levels)} mức Fibonacci Retracement.")


        # 5. Lưu ảnh (High Quality)
        fig.savefig(filename, bbox_inches='tight', pad_inches=0.1, dpi=300, facecolor=fig.get_facecolor())
        plt.close(fig)
        
        logger.info(f"✅ Đã lưu chart Pro Style tại: {filename}")
        return filename

    except Exception as e:
        logger.error(f"❌ Lỗi vẽ chart: {e}")
        return None

# Hàm get_technical_analysis - Simplified version
def get_technical_analysis(df: pd.DataFrame) -> str:
    """
    Phân tích kỹ thuật đơn giản - CHỈ trả về 3 thông tin:
    - Giá hiện tại
    - Hỗ trợ (Support) từ Fibonacci
    - Kháng cự (Resistance) từ Fibonacci
    
    Args:
        df: DataFrame chứa dữ liệu OHLC
    
    Returns:
        str: Chuỗi phân tích với 3 thông tin chính
    """
    try:
        if df is None or df.empty:
            return "Không có dữ liệu để phân tích."
        
        # Lấy giá hiện tại
        current_price = df['Close'].iloc[-1]
        
        # Tính Support/Resistance dựa trên Fibonacci
        fibo_levels = calculate_fibonacci_levels(df, window=100)
        
        support_level = None
        resistance_level = None
        support_name = ""
        resistance_name = ""
        
        if fibo_levels:
            # Tìm Support: Mức Fibonacci gần nhất phía dưới giá hiện tại
            # Tìm Resistance: Mức Fibonacci gần nhất phía trên giá hiện tại
            for level_name, price in fibo_levels.items():
                if price < current_price:
                    if support_level is None or price > support_level:
                        support_level = price
                        support_name = level_name
                elif price > current_price:
                    if resistance_level is None or price < resistance_level:
                        resistance_level = price
                        resistance_name = level_name
        
        # Format kết quả - CHỈ 3 THÔNG TIN
        support_str = f"{support_level:.2f} (Fibo {support_name})" if support_level else "N/A"
        resistance_str = f"{resistance_level:.2f} (Fibo {resistance_name})" if resistance_level else "N/A"
        
        summary = f"""
- Giá hiện tại: {current_price:.2f}
- Hỗ trợ: {support_str}
- Kháng cự: {resistance_str}
        """
        return summary.strip()
        
    except Exception as e:
        logger.error(f"❌ Lỗi get_technical_analysis: {e}")
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
            n_bars=100
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
        
        # 4.5 CHUẨN BỊ VOLUME BARS (Xanh/Đỏ)
        # Tách volume thành 2 series: up và down
        volume_up = df['Volume'].copy()
        volume_down = df['Volume'].copy()
        
        for i in range(len(df)):
            if df['Close'].iloc[i] >= df['Open'].iloc[i]:
                # Nến tăng - chỉ hiện volume_up
                volume_down.iloc[i] = np.nan
            else:
                # Nến giảm - chỉ hiện volume_down
                volume_up.iloc[i] = np.nan
        
        # Tạo 2 addplot riêng cho volume up và down dưới dạng bars
        apds = [
            mpf.make_addplot(volume_up, panel=1, color=up_color, 
                           type='bar', width=0.8, alpha=0.8, ylabel='Volume'),
            mpf.make_addplot(volume_down, panel=1, color=down_color, 
                           type='bar', width=0.8, alpha=0.8)
        ]
        
        # 5. Vẽ biểu đồ (Simple, No Indicators)
        fig, axlist = mpf.plot(
            df,
            type='candle',
            style=s,
            volume=False,  # Tắt volume mặc định
            addplot=apds,  # Thêm volume custom
            panel_ratios=(3, 1),  # Tỷ lệ giữa price panel và volume panel
            title="",
            ylabel='',
            datetime_format='%d/%m %H:%M',
            xrotation=0,
            figsize=(14, 9),  # Tăng chiều cao cho volume panel
            tight_layout=True,
            returnfig=True,
            savefig=filename
        )
        
        # 5.5 CẤU HÌNH VOLUME PANEL
        # Set volume y-axis limits
        if len(axlist) > 1:
            volume_ax = axlist[1]
            volume_ax.set_ylim(0, 55100)
        
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
        
        # 7.1 VẼ CÁC MỨC FIBONACCI RETRACEMENT
        fibo_levels = calculate_fibonacci_levels(df, window=100)
        
        if fibo_levels:
            fibo_color = '#1E90FF'  # Dodger Blue color
            
            for level_name, price in fibo_levels.items():
                # Xác định độ đậm dựa trên mức quan trọng
                if level_name == '0.618':  # Golden Ratio - quan trọng nhất
                    alpha = 0.9
                    linewidth = 0.7
                elif level_name == '0.5':  # Mức 50% - quan trọng
                    alpha = 0.8
                    linewidth = 0.6
                else:
                    alpha = 0.6
                    linewidth = 0.6
                
                # Vẽ đường ngang Fibonacci
                ax.axhline(y=price, color=fibo_color, linestyle='-', 
                          linewidth=linewidth, alpha=alpha, zorder=1)
                
                # Vẽ nhãn giá bên phải
                ax.text(
                    1.002, price,
                    f' Fibo {level_name}: {price:.2f} ',
                    transform=ax.get_yaxis_transform(),
                    color=fibo_color,
                    fontsize=8,
                    fontweight='bold' if level_name in ['0.618', '0.5'] else 'normal',
                    va='center', ha='left',
                    alpha=alpha,
                    bbox=dict(
                        boxstyle="square,pad=0.2",
                        facecolor=bg_color,
                        edgecolor=fibo_color,
                        alpha=0.7,
                        linewidth=0.5
                    )
                )
            
            logger.info(f"✅ Đã vẽ {len(fibo_levels)} mức Fibonacci Retracement.")

        
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