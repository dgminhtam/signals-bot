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
    """Fallback 2: Lấy dữ liệu từ TradingView"""
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

def get_data_from_yfinance(symbol: str = "XAUUSD", period: str = "5d", interval: str = "1h") -> Optional[pd.DataFrame]:
    """Fallback 3: Lấy dữ liệu từ yfinance nếu cả MT5 và TradingView đều chết"""
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

def get_market_data(symbol: str = "XAUUSD") -> Tuple[Optional[pd.DataFrame], str]:
    """
    Hàm trung tâm để lấy dữ liệu thị trường theo thứ tự: MT5 -> TradingView -> yfinance
    Trả về (DataFrame, source_name)
    """
    logger.info(f"📊 Đang lấy dữ liệu thị trường cho {symbol}...")
    
    df = None
    
    # 1. Thử MT5 trước (Primary)
    client = MT5DataClient()
    if client.connect():
        logger.info("🔌 Kết nối MT5 thành công, đang lấy dữ liệu...")
        df = client.get_historical_data(symbol, timeframe="H1", count=120)
        client.disconnect()
        if df is not None and not df.empty:
            logger.info(f"✅ Đã lấy dữ liệu từ MT5")
            return df, "MT5"
    else:
        logger.warning("⚠️ Không thể kết nối MT5.")

    # 2. Fallback 1: TradingView
    logger.warning("⚠️ Chuyển sang TradingView...")
    df = get_data_from_tradingview(symbol)
    if df is not None and not df.empty:
        logger.info(f"✅ Đã lấy dữ liệu từ TradingView")
        return df, "TradingView"
    
    # 3. Fallback 2: yfinance
    logger.warning("⚠️ TradingView không khả dụng, chuyển sang yfinance...")
    df = get_data_from_yfinance(symbol)
    if df is not None and not df.empty:
        logger.info(f"✅ Đã lấy dữ liệu từ yfinance")
        return df, "yfinance"
    
    logger.error("❌ Không thể lấy dữ liệu từ cả 3 nguồn")
    return None, "None"

def calculate_fibonacci_levels(df: pd.DataFrame, window: int = 120) -> Dict[str, float]:
    """
    Tính toán các mức Fibonacci Retracement dựa trên window nến gần nhất
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


def _analyze_trend(df: pd.DataFrame) -> str:
    """
    Xác định xu hướng nhanh dựa trên Price vs SMA20
    Returns: "UP" | "DOWN" | "NEUTRAL"
    """
    try:
        if len(df) < 20:
             # Fallback to Price vs Prev Close if not enough data
             return "UP" if df['Close'].iloc[-1] >= df['Close'].iloc[-2] else "DOWN"
        
        sma20 = df['Close'].tail(20).mean()
        current_price = df['Close'].iloc[-1]
        
        return "UP" if current_price >= sma20 else "DOWN"
    except:
        return "NEUTRAL"

def _prepare_volume_plots(plot_df: pd.DataFrame, up_color: str, down_color: str) -> list:
    """
    Tách logic xử lý indicator volume - trả về list addplot
    Màu sắc dựa trên sự thay đổi Volume (Lớn hơn nến trước -> Xanh, Nhỏ hơn -> Đỏ)
    """
    try:
        # DEBUG: Print Volume Values (Exclude NaNs from padding)
        valid_vol = plot_df['Volume'].dropna()
        logger.info(f"🔎 Valid Volume Stats: Max={valid_vol.max()}, Min={valid_vol.min()}")
        logger.info(f"🔎 Last 20 Valid Volumes: {valid_vol.tail(20).tolist()}")
        
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

def draw_price_chart(symbol: str = "XAUUSD", df: Optional[pd.DataFrame] = None, data_source: str = "Unknown") -> Optional[str]:
    """
    Vẽ biểu đồ giá với Fibonacci levels
    
    Args:
        symbol: Symbol để vẽ (dùng cho tiêu đề)
        df: DataFrame chứa dữ liệu OHLC (nếu None sẽ tự động lấy)
        data_source: Tên nguồn dữ liệu (để hiển thị và quyết định vẽ Volume)
    """
    logger.info(f"📈 Đang vẽ biểu đồ H1 (Pro Dark Style) cho {symbol}...")
    
    try:
        # Nếu không có DataFrame, tự động lấy dữ liệu
        if df is None:
            df, source = get_market_data(symbol)
            if df is None or df.empty:
                logger.error("❌ Không thể lấy dữ liệu để vẽ biểu đồ.")
                return None
            data_source = source
        
        # Decision: Draw Volume only if source is MT5
        draw_volume = (data_source == "MT5")

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
            gridstyle=':',          # Lưới chấm bi
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

        # 3. CHUẨN BỊ VOLUME BARS (Chỉ khi draw_volume=True)
        apds = []
        if draw_volume:
            apds = _prepare_volume_plots(plot_df, up_color, down_color)
            
        # 3. VẼ BIỂU ĐỒ
        # Nếu vẽ volume thì panel_ratios=(3, 1), nếu không thì không cần panel 1
        panel_ratios = (3, 1) if draw_volume else (1, 0)

        # 3. VẼ BIỂU ĐỒ
        # Nếu vẽ volume thì panel_ratios=(3, 1), nếu không thì không cần panel 1
        panel_ratios = (3, 1) if draw_volume else (1, 0) # mplfinance might complain about 0 ratio, let's see logic below
        
        # Logic: If volume=False in mpf.plot, it uses panel 0 for price. 
        # If we pass addplot with panel=1, we need to ensure mpf allocates panels.
        # Simple fix: just don't pass panel_ratios if no volume, or pass simple tuple.
        
        kwargs = dict(
            type='candle', 
            style=s, 
            volume=False,  # Luôn tắt volume mặc định để dùng custom addplot HOẶC không vẽ
            title="", 
            ylabel='', 
            datetime_format='%d/%m %H:%M',
            xrotation=0, 
            figsize=(14, 9),  
            tight_layout=True,
            returnfig=True,
            savefig=filename,
            update_width_config=dict(candle_width=0.6) # Narrow gap by widening candles
        )
        
        if draw_volume:
            kwargs['addplot'] = apds
            kwargs['panel_ratios'] = (3, 1)
        else:
             # Không addplot volume -> Chỉ có panel 0
             pass
        
        fig, axlist = mpf.plot(plot_df, **kwargs)

        # 4. CẤU HÌNH VOLUME PANEL (Nếu có)
        if draw_volume and len(axlist) > 1:
            # Determine Volume Axis
            # With y_on_right=True, axlist structure can be complex (Main, TwinMain, Panel1, TwinPanel1...)
            # We try to identify the volume axis (Panel 1)
            # Usually Panel 1 axes appear after Panel 0 axes.
            
            volume_ax = None
            if len(axlist) >= 3:
                volume_ax = axlist[2] # Typical for [Main, MainTwin, Vol]
            elif len(axlist) >= 2:
                volume_ax = axlist[1]
                
            if volume_ax:
                max_vol = plot_df['Volume'].max()
                if pd.notna(max_vol) and max_vol > 0:
                     # Log data for debugging
                    logger.info(f"📊 Volume Stats: Max={max_vol}, Min={plot_df['Volume'].min()}")
                    # Set limit to 1.1x max to avoid clipping
                    volume_ax.set_ylim(0, max_vol * 1.1)

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
        fibo_levels = calculate_fibonacci_levels(df, window=140)
        
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
                try:
                    perc_label = f"{float(level_name)*100:g}"
                except:
                    perc_label = level_name

                ax.text(
                    1.002, price,
                    f' Fibo {perc_label}: {price:.2f} ',
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
            
        # 4.3 VẼ MŨI TÊN XU HƯỚNG (AI VIEWPOINT)
        trend = _analyze_trend(df)
        arrow_color = up_color if trend == "UP" else down_color
        arrow_text = "TĂNG" if trend == "UP" else "GIẢM"
        
        # Vị trí: Góc trên bên phải, dưới Price Tag
        # Dùng transAxes để cố định vị trí trên khung hình
        ax.annotate(
            f"Xu hướng: {arrow_text}", 
            xy=(0.95, 0.92), xycoords='axes fraction',
            xytext=(0.95, 0.92), textcoords='axes fraction',
            fontsize=12, fontweight='bold', color=arrow_color,
            ha='right', va='top',
            bbox=dict(boxstyle="round,pad=0.3", fc=bg_color, ec=arrow_color, alpha=0.8)
        )
        
        # Vẽ mũi tên biểu tượng to hơn bên cạnh text
        arrow_marker = '▲' if trend == "UP" else '▼'
        ax.text(
            0.96, 0.92, arrow_marker, 
            transform=ax.transAxes,
            color=arrow_color, fontsize=18, fontweight='bold',
            ha='left', va='top'
        )

        # 5. Lưu ảnh (High Quality)
        fig.savefig(filename, bbox_inches='tight', pad_inches=0.1, dpi=300, facecolor=fig.get_facecolor())
        plt.close(fig)
        
        logger.info(f"✅ Đã lưu chart Price ({data_source}) tại: {filename}")
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
        fibo_levels = calculate_fibonacci_levels(df, window=120)
        
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
        
        # Calculate Volume Data
        current_vol = df['Volume'].iloc[-1]
        prev_vol = df['Volume'].iloc[-2] if len(df) > 1 else current_vol
        vol_avg_20 = df['Volume'].tail(20).mean()
        vol_signal = "TĂNG" if current_vol >= prev_vol else "GIẢM"
        
        # Format kết quả - CHỈ 3 THÔNG TIN
        # Helper func to format fibo name
        def fmt_fibo(name):
            try:
                return f"{float(name)*100:g}"
            except:
                return name

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
        # Check traceback
        import traceback
        traceback.print_exc()
        logger.error(f"❌ Lỗi get_technical_analysis: {e}")
        return "Lỗi tính toán."

if __name__ == "__main__":
    # Test Full Flow
    try:
        df, source = get_market_data("XAUUSD")
        if df is not None:
             # Test Technical Analysis
            print("--- Technical Analysis ---")
            print(get_technical_analysis(df))
            print("--------------------------")
            
            # Draw Chart
            draw_price_chart("XAUUSD", df, source)
    except Exception as e:
        logger.error(f"Test Failed: {e}")

