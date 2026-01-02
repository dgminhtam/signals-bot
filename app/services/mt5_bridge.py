import asyncio
import pandas as pd
import io
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional

class MT5DataClient:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MT5DataClient, cls).__new__(cls)
        return cls._instance

    def __init__(self, host='127.0.0.1', port=1122):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        
        # Mapping timeframe
        self.TIMEFRAMES = {
            'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30,
            'H1': 16385, 'H4': 16388, 'D1': 16408
        }
        self._initialized = True

    async def connect(self) -> bool:
        """
        Mở kết nối Socket đến MT5 (Async)
        """
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=5
            )
            return True
        except Exception as e:
            print(f"❌ Exception connecting to MT5 {self.host}:{self.port} -> {e}") 
            return False

    async def disconnect(self):
        """
        Đóng kết nối (Async)
        """
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
            self.writer = None
            self.reader = None

    async def get_historical_data(self, symbol="XAUUSD", timeframe="H1", count=120):
        """
        Gửi lệnh lấy dữ liệu nến (Async)
        """
        if not self.writer:
            if not await self.connect():
                return None

        try:
            # Gửi lệnh theo protocol: SYMBOL|TIMEFRAME|COUNT
            command = f"{symbol}|{timeframe}|{count}"
            self.writer.write(command.encode())
            await self.writer.drain()
            
            # Nhận dữ liệu (Buffer)
            data = b""
            while True:
                try:
                    # Timeout cho mỗi lần đọc chunk
                    chunk = await asyncio.wait_for(self.reader.read(4096), timeout=5)
                    if not chunk: break
                    data += chunk
                    # Nếu buffer nhỏ hơn 4096 nghĩa là đã hết tin (với EA simple)
                    if len(chunk) < 4096: break 
                except asyncio.TimeoutError:
                    break
            
            response_str = data.decode('utf-8', errors='ignore').strip()
            
            if not response_str or response_str.startswith("ERROR"):
                return None

            # Parse CSV off-thread (CPU bound) nếu quá nặng? 
            # Hiện tại vẫn parse sync vì pandas read_csv nhanh với data nhỏ.
            # Parse CSV: Time,Open,High,Low,Close,Volume
            csv_str = response_str.replace(";", "\n")
            
            df = pd.read_csv(io.StringIO(csv_str), header=None, 
                             names=["Time", "Open", "High", "Low", "Close", "Volume"])
            
            # Xử lý datetime
            df['Time'] = pd.to_datetime(df['Time'], unit='s')
            df.set_index('Time', inplace=True)
            
            # Convert múi giờ
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC')
            df.index = df.index.tz_convert('Asia/Ho_Chi_Minh')
            
            # Ensure data is sorted by Time (Ascending)
            df.sort_index(inplace=True)
            
            return df

        except Exception as e:
            print(f"❌ Lỗi lấy data: {e}")
            return None

    async def _send_simple_command(self, command: str) -> str:
        """
        Gửi lệnh và nhận phản hồi ngắn (Async)
        Có cơ chế Retry nếu mất kết nối
        """
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            # Ensure connection
            if not self.writer:
                if not await self.connect():
                    await asyncio.sleep(1)
                    continue
            
            try:
                self.writer.write(command.encode())
                await self.writer.drain()
                
                # Wait for response with timeout
                chunk = await asyncio.wait_for(self.reader.read(4096), timeout=5)
                
                if not chunk:
                    # Connection closed by peer
                    raise ConnectionResetError("Empty response, connection closed by peer")
                    
                response = chunk.decode('utf-8').strip()
                
                # --- FIX: Chủ động đóng kết nối sau mỗi lệnh thành công ---
                # Điều này đồng bộ với hành vi của EA (Server đóng ngay sau khi gửi)
                await self.disconnect()
                # ---------------------------------------------------------
                
                return response
                
            except (ConnectionError, OSError, asyncio.TimeoutError) as e:
                last_error = e
                print(f"⚠️ Socket error ({e}). Reconnecting ({attempt+1}/{max_retries})...")
                await self.disconnect()
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"❌ Unexpected error sending command: {e}")
                await self.disconnect()
                return f"FAIL|EXCEPTION|{e}"
                
        return f"FAIL|CONNECTION_ERROR|{last_error}"

    async def execute_order(self, symbol: str, order_type: str, volume: float, sl: float, tp: float, price: float = 0.0) -> str:
        """
        Gửi lệnh giao dịch: ORDER|SYMBOL|TYPE|VOL|SL|TP|PRICE (Async)
        Price is mandatory for Pending Orders (BUY_STOP, SELL_STOP).
        """
        command = f"ORDER|{symbol}|{order_type}|{volume}|{sl}|{tp}|{price}"
        return await self._send_simple_command(command)

    async def execute_order_relative(self, symbol: str, order_type: str, volume: float, sl_points: float, tp_points: float) -> str:
        """
        Gửi lệnh giao dịch Relative (Fast execution for News):
        ORDER_REL|SYMBOL|TYPE|VOL|SL_POINTS|TP_POINTS
        """
        command = f"ORDER_REL|{symbol}|{order_type}|{volume}|{sl_points}|{tp_points}"
        return await self._send_simple_command(command)

    async def get_open_positions(self, symbol: str = "ALL") -> List[Dict]:
        """
        Lấy danh sách lệnh đang mở (Async).
        """
        command = f"CHECK|{symbol}"
        response = await self._send_simple_command(command)
        
        if not response or response == "EMPTY" or response.startswith("FAIL") or response.startswith("ERROR"):
            return []
        
        try:
            # Parse logic kept sync as it is fast string manipulation
            positions = []
            items = response.split(";")
            
            for item in items:
                if not item.strip(): continue
                parts = item.split(",")
                
                # Format: TICKET,TYPE,PRICE,VOL,PROFIT,SL,TP
                if len(parts) >= 7:
                    pos = {
                        "ticket": int(parts[0]),
                        "type": "BUY" if int(parts[1]) == 0 else "SELL",
                        "open_price": float(parts[2]),
                        "volume": float(parts[3]),
                        "profit": float(parts[4]),
                        "sl": float(parts[5]),
                        "tp": float(parts[6])
                    }
                    positions.append(pos)
                elif len(parts) >= 5: # Fallback for older EA (no SL/TP)
                    pos = {
                        "ticket": int(parts[0]),
                        "type": "BUY" if int(parts[1]) == 0 else "SELL",
                        "open_price": float(parts[2]),
                        "volume": float(parts[3]),
                        "profit": float(parts[4]),
                        "sl": 0.0,
                        "tp": 0.0
                    }
                    positions.append(pos)
                elif len(parts) >= 4: # Fallback for very old EA
                    pos = {
                        "ticket": int(parts[0]),
                        "type": "BUY" if int(parts[1]) == 0 else "SELL",
                        "volume": float(parts[2]),
                        "profit": float(parts[3]),
                        "open_price": 0.0,
                        "sl": 0.0,
                        "tp": 0.0
                    }
                    positions.append(pos)
            
            return positions
        except Exception as e:
            print(f"❌ Lỗi parse positions: {e}")
            return []

    async def close_order(self, ticket: int) -> str:
        """
        Đóng lệnh theo Ticket: CLOSE|TICKET (Async)
        """
        command = f"CLOSE|{ticket}"
        return await self._send_simple_command(command)

    async def delete_order(self, ticket: int) -> str:
        """
        Xóa lệnh chờ (Pending Order) theo Ticket: DELETE|TICKET (Async)
        """
        command = f"DELETE|{ticket}"
        return await self._send_simple_command(command)

    async def get_trade_history(self, ticket: int) -> Optional[Dict]:
        """
        Lấy thông tin lệnh đã đóng từ lịch sử.
        Format mới: SUCCESS|O_PRICE|C_PRICE|PROFIT|SL|TP|O_TIME|C_TIME
        """
        command = f"HISTORY|{ticket}"
        try:
            response = await self._send_simple_command(command)
            
            if response and response.startswith("SUCCESS"):
                parts = response.split("|")
                
                # Kiểm tra độ dài tối thiểu (SUCCESS + 3 fields min)
                if len(parts) < 4: return None

                result = {
                    'open_price': float(parts[1]) if len(parts) > 1 else 0.0,
                    'close_price': float(parts[2]) if len(parts) > 2 else 0.0,
                    'profit': float(parts[3]) if len(parts) > 3 else 0.0,
                    'status': 'CLOSED'
                }
                
                # Parse SL/TP
                if len(parts) > 5:
                    result['sl'] = float(parts[4])
                    result['tp'] = float(parts[5])
                
                # Parse Time (Open & Close)
                if len(parts) > 7:
                    result['open_time'] = int(parts[6])
                    result['close_time'] = int(parts[7])
                
                return result
            
            return None
            
        except Exception as e:
            print(f"❌ Error getting trade history for {ticket}: {e}")
            return None