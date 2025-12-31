import os

file_path = r"d:\Internal\signals-bot\app\core\database.py"

try:
    with open(file_path, "rb") as f:
        content_bytes = f.read()

    # Convert to string treating it as mostly utf-8, ignoring errors to pass garbage
    content_str = content_bytes.decode("utf-8", errors="ignore")

    # 1. Clean up garbage at the end
    # Find the end of get_trade_metadata
    marker = 'logger.error(f"❌ Lỗi get_trade_metadata for ticket {ticket}: {e}.")\r\n        return None'
    marker_pos = content_str.find(marker.replace('\r\n', '\n'))
    if marker_pos == -1:
        marker = 'logger.error(f"❌ Lỗi get_trade_metadata for ticket {ticket}: {e}.")\n        return None'
        marker_pos = content_str.find(marker)
    
    if marker_pos != -1:
        # Keep content up to the marker + length of marker
        end_pos = marker_pos + len(marker)
        clean_content = content_str[:end_pos] + "\n\n"
    else:
        # If marker not found, rely on backup or try to strip null bytes
        print("Marker not found, attempting to just strip nulls and wide chars")
        clean_content = content_str.replace('\x00', '')
    
    # 2. Add sync_trade_data
    sync_func = '''async def sync_trade_data(ticket: int, open_price: float, close_price: float, profit: float, sl: float, tp: float, open_time: int, close_time: int) -> bool:
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
    clean_content += sync_func

    # 3. Remove the bad line in update_trade_exit
    bad_line = 'sql += ", close_time = COALESCE(close_time, CURRENT_TIMESTAMP)" # Logic fallback cho chắc chắn'
    if bad_line in clean_content:
        clean_content = clean_content.replace(bad_line, '')
        print("Removed redundant close_time line.")
    else:
        print("Redundant line not found (might match partially). Checking loose match.")
        
    # Write back
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(clean_content)
    
    print("Successfully repaired database.py")

except Exception as e:
    print(f"Error repairing file: {e}")
