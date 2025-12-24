"""
Test Script for Trade Storage System
Verifies database schema and basic CRUD operations
"""

import asyncio
import aiosqlite
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import database, config

async def test_database_schema():
    """Test that trade_history table exists with correct columns"""
    print("=" * 60)
    print("TEST 1: Database Schema Verification")
    print("=" * 60)
    
    try:
        async with database.get_db_connection() as conn:
            # Check if table exists
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='trade_history'"
            ) as cursor:
                result = await cursor.fetchone()
                
            if result:
                print("✅ Table 'trade_history' exists")
                
                # Check columns
                async with conn.execute("PRAGMA table_info(trade_history)") as cursor:
                    columns = await cursor.fetchall()
                
                expected_columns = {
                    'ticket', 'signal_id', 'symbol', 'order_type', 'volume',
                    'open_price', 'sl', 'tp', 'close_price', 'profit',
                    'status', 'open_time', 'close_time'
                }
                
                actual_columns = {col[1] for col in columns}
                
                if expected_columns.issubset(actual_columns):
                    print("✅ All required columns present")
                    print(f"   Columns: {', '.join(sorted(actual_columns))}")
                    return True
                else:
                    missing = expected_columns - actual_columns
                    print(f"❌ Missing columns: {missing}")
                    return False
            else:
                print("❌ Table 'trade_history' does not exist")
                return False
                
    except Exception as e:
        print(f"❌ Error checking schema: {e}")
        return False

async def test_save_trade_entry():
    """Test saving a new trade entry"""
    print("\n" + "=" * 60)
    print("TEST 2: Save Trade Entry")
    print("=" * 60)
    
    try:
        # Create a test trade
        test_ticket = 999999
        result = await database.save_trade_entry(
            ticket=test_ticket,
            signal_id=None,
            symbol="XAUUSD",
            order_type="BUY",
            volume=0.01,
            open_price=2650.50,
            sl=2640.50,
            tp=2670.50
        )
        
        if result:
            print("✅ Trade entry saved successfully")
            
            # Verify it was saved
            async with database.get_db_connection() as conn:
                async with conn.execute(
                    "SELECT * FROM trade_history WHERE ticket = ?", (test_ticket,)
                ) as cursor:
                    row = await cursor.fetchone()
                
                if row:
                    print(f"✅ Trade verified in database")
                    print(f"   Ticket: {row['ticket']}, Symbol: {row['symbol']}, Type: {row['order_type']}")
                    print(f"   Status: {row['status']}, Volume: {row['volume']}")
                    return True
                else:
                    print("❌ Trade not found in database")
                    return False
        else:
            print("❌ Failed to save trade entry")
            return False
            
    except Exception as e:
        print(f"❌ Error testing save: {e}")
        return False

async def test_get_open_trades():
    """Test fetching open trades"""
    print("\n" + "=" * 60)
    print("TEST 3: Get Open Trades")
    print("=" * 60)
    
    try:
        open_trades = await database.get_open_trades()
        print(f"✅ Retrieved {len(open_trades)} open trades")
        
        for trade in open_trades:
            print(f"   - Ticket #{trade['ticket']}: {trade['order_type']} {trade['symbol']} (Status: {trade['status']})")
        
        return True
        
    except Exception as e:
        print(f"❌ Error fetching open trades: {e}")
        return False

async def test_update_trade_exit():
    """Test updating a trade as closed"""
    print("\n" + "=" * 60)
    print("TEST 4: Update Trade Exit")
    print("=" * 60)
    
    try:
        test_ticket = 999999
        result = await database.update_trade_exit(
            ticket=test_ticket,
            close_price=2665.25,
            profit=147.50,
            status='CLOSED'
        )
        
        if result:
            print("✅ Trade exit updated successfully")
            
            # Verify status changed
            async with database.get_db_connection() as conn:
                async with conn.execute(
                    "SELECT status, close_price, profit FROM trade_history WHERE ticket = ?", 
                    (test_ticket,)
                ) as cursor:
                    row = await cursor.fetchone()
                
                if row and row['status'] == 'CLOSED':
                    print(f"✅ Status verified: {row['status']}")
                    print(f"   Close Price: {row['close_price']}, Profit: {row['profit']}")
                    return True
                else:
                    print("❌ Status not updated correctly")
                    return False
        else:
            print("❌ Failed to update trade exit")
            return False
            
    except Exception as e:
        print(f"❌ Error testing update: {e}")
        return False

async def cleanup_test_data():
    """Clean up test trade"""
    print("\n" + "=" * 60)
    print("CLEANUP: Removing test data")
    print("=" * 60)
    
    try:
        async with database.get_db_connection() as conn:
            await conn.execute("DELETE FROM trade_history WHERE ticket = 999999")
            await conn.commit()
        print("✅ Test data cleaned up")
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")

async def main():
    """Run all tests"""
    print("\n🧪 TRADE STORAGE SYSTEM - TEST SUITE")
    print("=" * 60)
    print(f"Database: {config.DB_NAME}")
    print("=" * 60)
    
    # Initialize database
    await database.init_db()
    
    # Run tests
    results = []
    results.append(await test_database_schema())
    results.append(await test_save_trade_entry())
    results.append(await test_get_open_trades())
    results.append(await test_update_trade_exit())
    
    # Cleanup
    await cleanup_test_data()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("✅ ALL TESTS PASSED")
    else:
        print(f"❌ {total - passed} TEST(S) FAILED")
    
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
