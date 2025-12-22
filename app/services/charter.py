# charter.py
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import numpy as np
from typing import Optional
import os
import sys

# Add project root to path to allow direct execution
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

from app.core import config
from app.services.ta_service import calculate_fibonacci_levels, analyze_trend

logger = config.logger
IMAGES_DIR = config.IMAGES_DIR

if not os.path.exists(IMAGES_DIR):
    os.makedirs(IMAGES_DIR)

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
        if df is None:
            logger.error("❌ DataFrame is None in draw_price_chart.")
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
        trend = analyze_trend(df, ai_trend)
        arrow_color = up_color if trend == "UP" else down_color
        arrow_text = "TĂNG" if trend == "UP" else "GIẢM"
        
        ax.annotate(f"Xu hướng: {arrow_text}", xy=(0.95, 0.92), xycoords='axes fraction',
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
