
import pandas as pd
from app.services.mt5_bridge import MT5DataClient

client = MT5DataClient()
if client.connect():
    df = client.get_historical_data("XAUUSD", timeframe="H1", count=100)
    client.disconnect()
    if df is not None:
        print("Last 20 Volume Values:")
        print(df['Volume'].tail(20).tolist())
        print(f"Max: {df['Volume'].max()}, Min: {df['Volume'].min()}")
    else:
        print("No data returned")
else:
    print("Could not connect to MT5")
