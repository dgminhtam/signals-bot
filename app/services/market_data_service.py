import pandas as pd
import yfinance as yf
from typing import Tuple, Optional
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from app.services.mt5_bridge import MT5DataClient
from app.core import config

logger = config.logger
loop = asyncio.get_event_loop()

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
    Hàm trung tâm để lấy dữ liệu thị trường theo thứ tự: MT5 (Retry 3 lần) -> TradingView -> yfinance
    Trả về (DataFrame, source_name)
    """
    logger.info(f"📊 Đang lấy dữ liệu thị trường cho {symbol}...")
    
    df = None
    
    # 1. Thử MT5 trước (Primary) với Smart Retry
    MT5_MAX_RETRIES = 3
    for attempt in range(1, MT5_MAX_RETRIES + 1):
        try:
            client = MT5DataClient()
            if await client.connect():
                df = await client.get_historical_data(symbol, timeframe="H1", count=120)
                await client.disconnect()
                
                if df is not None and not df.empty:
                    logger.info(f"✅ Đã lấy dữ liệu từ MT5 (Attempt {attempt}/{MT5_MAX_RETRIES})")
                    return df, "MT5"
                else:
                    logger.warning(f"⚠️ MT5 connected but returned no data (Attempt {attempt}/{MT5_MAX_RETRIES}).")
            else:
                 logger.warning(f"⚠️ MT5 connection failed (Attempt {attempt}/{MT5_MAX_RETRIES}).")
        except Exception as e:
            logger.warning(f"⚠️ Error accessing MT5 (Attempt {attempt}/{MT5_MAX_RETRIES}): {e}")
        
        # Nếu chưa phải lần cuối, sleep 1 chút để retry
        if attempt < MT5_MAX_RETRIES:
            logger.info("   ...Retrying MT5 in 1.5s...")
            await asyncio.sleep(1.5)

    logger.warning("❌ Hết số lần thử MT5. Chuyển sang Fallback...")

    # 2. Fallback 1: TradingView (Sync wrapped in Executor)
    logger.warning("⚠️ Chuyển sang TradingView...")
    try:
        # Use loop.run_in_executor to avoid blocking the event loop
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
