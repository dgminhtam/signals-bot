import socket
import pandas as pd
import io
import time
from typing import List, Dict, Optional

class MT5DataClient:
    def __init__(self, host='127.0.0.1', port=1122):
        self.host = host
        self.port = port
        self.sock = None
        
        # Mapping timeframe
        self.TIMEFRAMES = {
            'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30,
            'H1': 16385, 'H4': 16388, 'D1': 16408
        }

    def connect(self) -> bool:
        """
        Mở kết nối Socket đến MT5
        """
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5) # Timeout 5 giây
            self.sock.connect((self.host, self.port))
            return True
        except Exception as e:
            print(f"❌ Exception connecting to MT5 {self.host}:{self.port} -> {e}") 
            return False

    def disconnect(self):
        """
        Đóng kết nối
        """
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None

    def get_historical_data(self, symbol="XAUUSD", timeframe="H1", count=120):
        """
        Gửi lệnh lấy dữ liệu nến
        """
        if not self.sock:
            if not self.connect():
                return None

        try:
            # Lấy mã timeframe
            tf_code = self.TIMEFRAMES.get(timeframe, 16385)
            
            # Gửi lệnh theo protocol: SYMBOL|TIMEFRAME|COUNT
            command = f"{symbol}|{timeframe}|{count}"
            self.sock.send(command.encode())
            
            # Nhận dữ liệu (Buffer)
            data = b""
            while True:
                try:
                    chunk = self.sock.recv(4096)
                    if not chunk: break
                    data += chunk
                    # Nếu buffer nhỏ hơn 4096 nghĩa là đã hết tin (với EA simple)
                    if len(chunk) < 4096: break 
                except socket.timeout:
                    break
            
            response_str = data.decode('utf-8', errors='ignore').strip()
            
            if not response_str or response_str.startswith("ERROR"):
                return None

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
            
            return df

        except Exception as e:
            print(f"❌ Lỗi lấy data: {e}")
            return None

    def execute_order(self, symbol: str, order_type: str, volume: float, sl: float, tp: float) -> str:
        """
        Gửi lệnh giao dịch: ORDER|SYMBOL|TYPE|VOL|SL|TP
        """
        if not self.sock:
            if not self.connect():
                return "FAIL|NO_CONNECTION"
        
        try:
            # Format: ORDER|XAUUSD|BUY|0.01|2000.0|2050.0
            command = f"ORDER|{symbol}|{order_type}|{volume}|{sl}|{tp}"
            self.sock.send(command.encode())
            
            response = self.sock.recv(4096).decode('utf-8').strip()
            return response
        except Exception as e:
            print(f"❌ Lỗi gửi lệnh: {e}")
            return f"FAIL|EXCEPTION|{e}"

    def get_open_positions(self, symbol: str = "ALL") -> List[Dict]:
        """
        Lấy danh sách lệnh đang mở.
        Trả về: List of Dictionaries [{'ticket': 123, 'type': 'BUY', 'volume': 0.1, 'profit': 10.5}]
        """
        if not self.sock:
            if not self.connect():
                return []
            
        try:
            command = f"CHECK|{symbol}"
            self.sock.send(command.encode())
            
            response = self.sock.recv(4096).decode('utf-8').strip()
            
            if response == "EMPTY" or response.startswith("FAIL") or response.startswith("ERROR"):
                return []
            
            # Parse response: "123456,0,0.01,5.5;123457,1,0.02,-1.2;"
            positions = []
            items = response.split(";")
            
            for item in items:
                if not item.strip(): continue
                parts = item.split(",")
                if len(parts) >= 4:
                    pos = {
                        "ticket": int(parts[0]),
                        "type": "BUY" if int(parts[1]) == 0 else "SELL",
                        "volume": float(parts[2]),
                        "profit": float(parts[3])
                    }
                    positions.append(pos)
            
            return positions
            
        except Exception as e:
            print(f"❌ Lỗi check lệnh: {e}")
            return []

    def close_order(self, ticket: int) -> str:
        """
        Đóng lệnh theo Ticket: CLOSE|TICKET
        """
        if not self.sock:
            if not self.connect():
                return "FAIL|NO_CONNECTION"
        
        try:
            command = f"CLOSE|{ticket}"
            self.sock.send(command.encode())
            
            response = self.sock.recv(4096).decode('utf-8').strip()
            return response
        except Exception as e:
            print(f"❌ Lỗi đóng lệnh: {e}")
            return f"FAIL|EXCEPTION|{e}"