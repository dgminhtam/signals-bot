import os

file_path = r"d:\Internal\signals-bot\app\core\database.py"

try:
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 1. Normalize spacing: Remove blank lines if there are too many, 
    # but simplest is just to write non-empty lines, or keeping max 1 empty line.
    # The file seemed to have EVERY line followed by a newline.
    
    normalized_lines = []
    for line in lines:
        if line.strip():
            normalized_lines.append(line)
        else:
            # Only append empty line if previous wasn't empty
            if normalized_lines and normalized_lines[-1].strip():
                normalized_lines.append(line)

    content = "".join(normalized_lines)

    # 2. Fix get_trade_metadata truncation
    # Find start of get_trade_metadata
    start_marker = "async def get_trade_metadata("
    start_pos = content.find(start_marker)
    
    if start_pos != -1:
        # Cut everything after start_marker
        content = content[:start_pos]
        
        # Append valid get_trade_metadata and sync_trade_data
        append_code = '''async def get_trade_metadata(ticket: int) -> Optional[Dict[str, Any]]:
    """
    Lấy metadata của trade từ signal (JOIN với trade_signals).
    Trả về {'source': str, 'score': float} nếu có signal_id.
    Trả về None nếu signal_id là NULL (Sniper/Straddle/Manual).
    """
    try:
        async with get_db_connection() as conn:
            async with conn.execute(\'\'\'
                SELECT ts.source, ts.score
                FROM trade_history th
                LEFT JOIN trade_signals ts ON th.signal_id = ts.id
                WHERE th.ticket = ?
            \'\'\', (ticket,)) as cursor:
                row = await cursor.fetchone()
                
                if not row:
                    logger.warning(f"Trade #{ticket} not found in database")
                    return None
                
                # If signal_id was NULL, the JOIN will return NULL for source/score
                if row['source'] is None:
                    return None  # No signal metadata (Sniper/Straddle/Manual)
                
                return {
                    'source': row['source'],
                    'score': row['score'] if row['score'] is not None else 0.0
                }
    except Exception as e:
        logger.error(f"❌ Lỗi get_trade_metadata for ticket {ticket}: {e}.")
        return None

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
                return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

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
        content += append_code
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("Successfully normalized and fixed database.py")
    else:
        print("Could not find get_trade_metadata to replace.")
        
except Exception as e:
    print(f"Error normalizing: {e}")
