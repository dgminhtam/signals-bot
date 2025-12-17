
import sys
import os
import time
from unittest.mock import MagicMock, patch

sys.path.append(os.getcwd())

from app.services.trader import AutoTrader
from app.core import database, config

# Use Test DB
config.DB_NAME = "test_trader_flow_v2.db"
database.DB_NAME = "test_trader_flow_v2.db"

def test_trader_integration():
    print("🚀 Starting Trader Integration Test (DB + News Flow)...")
    
    if os.path.exists(config.DB_NAME):
        os.remove(config.DB_NAME)
        
    # 1. Setup Mock MT5
    with patch('app.services.trader.MT5DataClient') as MockClient, \
         patch('app.services.trader.get_market_data') as MockMarket:
             
        mock_mt5 = MockClient.return_value
        mock_mt5.execute_order.return_value = "SUCCESS|123456"
        
        # Mock Market Data (Price 2000)
        import pandas as pd
        mock_df = pd.DataFrame({'Close': [2000.0], 'Volume': [100.0]})
        MockMarket.return_value = (mock_df, "MT5")
        
        trader = AutoTrader()
        
        # 2. Test NEWS Signal (DB Priority)
        print("\n[Test 1] Analyze with NEWS Signal in DB...")
        
        # Insert News Signal
        if os.path.exists(config.DB_NAME): os.remove(config.DB_NAME)
        database.init_db()
        database.save_trade_signal("XAUUSD", "SELL", "NEWS", 9.0)
        
        # Run Analyze
        res = trader.analyze_and_trade()
        print(f"👉 Result: {res}")
        
        # Verification
        # Should execute SELL immediately (Fast Track)
        # Check call args
        calls = mock_mt5.execute_order.call_args_list
        # Expecting: symbol='XAUUSD', type='SELL', vol=..., sl=2010 (2000+10), tp=1980 (2000-20)
        if calls:
            args = calls[0].args
            print(f"✅ Executed: {args}")
            if args[1] == 'SELL' and args[3] == 2010.0:
                 print("✅ Logic Correct: Sold at 2000, SL at 2010 (News Params).")
            else:
                 print(f"❌ Logic Error: SL/TP or Type mismatch. SL={args[3]}, TP={args[4]}")
        else:
            print("❌ No order executed!")
            
        
        # 3. Test AI Signal (Normal Track)
        print("\n[Test 2] Analyze with AI Signal...")
        mock_mt5.execute_order.reset_mock()
        
        # Insert AI Signal (Newer)
        time.sleep(1)
        database.save_trade_signal("XAUUSD", "BUY", "AI_REPORT", 7.0)
        
        # Run Analyze
        # Note: Logic prefers News if within TTL. Our News signal is < 1 min old.
        # So it MIGHT still pick News if get_latest_valid_signal prioritizes it.
        # Let's see. 
        res2 = trader.analyze_and_trade()
        print(f"👉 Result 2: {res2}")
        
        # Unless we delete News signal or wait TTL.
        # Let's manually delete news signal for this test case to force AI path.
        with database.get_db_connection() as conn:
            conn.execute("DELETE FROM trade_signals WHERE source='NEWS'")
            conn.commit()
            
        print("   (Deleted News signal to force AI path)")
        res3 = trader.analyze_and_trade()
        print(f"👉 Result 3 (AI Path): {res3}")
        
        calls_ai = mock_mt5.execute_order.call_args_list
        if calls_ai:
            args = calls_ai[0].args
            # AI Fallback: SL 5, TP 10
            # BUY at 2000 -> SL 1995, TP 2010
            print(f"✅ Executed AI: {args}")
            if args[1] == "BUY" and args[3] == 1995.0:
                 print("✅ Logic Correct: Buy at 2000, SL 1995 (AI Params).")
            else:
                 print(f"❌ Logic Error AI Params. SL={args[3]}")
        else:
             print("❌ No AI Order Executed (Maybe filtered by volume or news?)")


    print("\n✅ Test Completed.")

if __name__ == "__main__":
    try:
        test_trader_integration()
    finally:
        if os.path.exists(config.DB_NAME):
            try: os.remove(config.DB_NAME)
            except: pass
