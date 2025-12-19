
import asyncio
import sys
import os

# Ensure app is in path
sys.path.append(os.getcwd())

from app.services.trader import AutoTrader
from app.core import database
from app.core import config

async def test_straddle():
    print(">>> Initializing AutoTrader...")
    trader = AutoTrader("XAUUSD", volume=0.01)
    
    # Ensure client connects
    if not await trader.client.connect():
        print("❌ Failed to connect to MT5.")
        return

    print(">>> Testing place_straddle_orders...")
    # Use larger distance to avoid immediate execution during test
    tickets = await trader.place_straddle_orders(distance_pips=100, sl_pips=50, tp_pips=100)
    
    if not tickets:
        print("❌ No tickets returned. Check logs.")
    else:
        print(f"✅ Straddle Orders Placed: {tickets}")
        
        print(">>> Waiting 5 seconds...")
        await asyncio.sleep(5)
        
        print(">>> Testing cleanup_pending_orders...")
        await trader.cleanup_pending_orders(tickets)
        print("✅ Cleanup called.")
        
    await trader.client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(test_straddle())
    except KeyboardInterrupt:
        pass
