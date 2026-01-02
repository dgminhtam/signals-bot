import os

file_path = r"d:\Internal\signals-bot\app\core\database.py"

try:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Find the end of the last known good function
    marker = 'logger.error(f"❌ Lỗi get_trade_metadata for ticket {ticket}: {e}.")\n        return None'
    marker_pos = content.find(marker)
    
    if marker_pos == -1:
        print("Marker not found, analyzing end of file...")
        # Fallback: look for the last 'return None' indentation
        lines = content.splitlines()
        cut_index = -1
        for i, line in enumerate(lines):
             if 'async def get_trade_metadata' in line:
                 # Found the function, search for its end
                 for j in range(i, len(lines)):
                     if 'return None' in lines[j] and '        return None' in lines[j]: # Indentation check
                         cut_index = j + 1
                         break
        if cut_index != -1:
             content = '\n'.join(lines[:cut_index])
             print(f"Truncated at line {cut_index}")
        else:
             print("Could not find safe truncate point.")
             exit(1)
    else:
        # Cut after marker
        cut_pos = marker_pos + len(marker)
        content = content[:cut_pos]
        print("Truncated after marker.")

    # Append new function
    new_func = '''

async def sync_trade_data(ticket: int, open_price: float, close_price: float, profit: float, sl: float, tp: float, open_time: int, close_time: int) -> bool:
    """
    Đồng bộ toàn diện dữ liệu trade từ MT5 về DB (Full Sync).
    Tự động convert timestamp sang UTC.
    """
    try:
        async with get_db_connection() as conn:
            sql = \'\'\'
                UPDATE trade_history 
                SET open_price=?, close_price=?, profit=?, sl=?, tp=?, open_time=?, close_time=?
                WHERE ticket=?
            \'\'\'
            
            # Helper convert timestamp sang UTC String
            def to_utc_str(ts):
                if not ts or ts == 0: return None
                return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(\'%Y-%m-%d %H:%M:%S\')

            o_time_str = to_utc_str(open_time)
            c_time_str = to_utc_str(close_time)
            
            params = (open_price, close_price, profit, sl, tp, o_time_str, c_time_str, ticket)
            
            await conn.execute(sql, params)
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"❌ Lỗi sync_trade_data #{ticket}: {e}")
        return False
'''
    content += new_func

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print("Successfully re-wrote database.py")

except Exception as e:
    print(f"Error: {e}")
