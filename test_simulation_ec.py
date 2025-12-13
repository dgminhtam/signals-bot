"""
Script giả lập quá trình sự kiện kinh tế để test Telegram Alert & AI.
"""
import time
from datetime import datetime, timedelta
from dateutil import tz
from app.core import database
from app.services.economic_calendar import EconomicCalendarService
from app.core import config

# ID giả
FAKE_ID = "SIM_12345"

def run_simulation():
    svc = EconomicCalendarService()
    print("[INFO] Bat dau gia lap Economic Calendar...")

    # 1. SETUP PRE-NEWS STATE
    future_time = datetime.now(tz.UTC) + timedelta(minutes=30)
    
    fake_event_pre = {
        "id": FAKE_ID,
        "event": "US CPI m/m",
        "title": "SIMULATION: US CPI m/m (Tin Gia Lap)",
        "currency": "USD",
        "impact": "High",
        "timestamp": future_time.strftime('%Y-%m-%d %H:%M:%S'), 
        "forecast": "0.3%",
        "previous": "0.2%",
        "actual": "", 
        "status": "pending" 
    }
    
    print("\n[1] Upsert Data: Sap co tin (Pre-News)...")
    database.upsert_economic_event(fake_event_pre)
    database.update_event_status(FAKE_ID, 'pending')
    
    print(">> Dang chay check alerts...")
    
    # DEBUG: Test AI Scenarios locally
    from app.services import ai_engine
    print(">> DEBUG: AI dang phan tich kich ban Pre-News...")
    analysis = ai_engine.analyze_pre_economic_data(fake_event_pre)
    if analysis:
        # Avoid printing unicode if possible, or print dict safely
        print(f"Scenario High: {analysis.get('scenario_high', 'N/A')}")
        print(f"Scenario Low: {analysis.get('scenario_low', 'N/A')}")
    else:
        print("AI returned None")

    svc.process_calendar_alerts()
    print("[OK] Da xu ly Pre-Alert (Kiem tra Telegram!)")
    
    print("\nCho 10 giay gia lap thoi gian troi qua...")
    time.sleep(10)
    
    # 2. SETUP POST-NEWS STATE
    fake_event_post = fake_event_pre.copy()
    fake_event_post["actual"] = "0.5%" 
    
    print("\n[2] Update Data: Tin da ra (Post-News)...")
    database.upsert_economic_event(fake_event_post)
    
    print(">> Dang chay check alerts (Kem AI Analysis)...")
    svc.process_calendar_alerts()
    print("[OK] Da xu ly Post-Alert (Kiem tra Telegram + AI!)")

    print("\nHoan tat gia lap.")
    print(f"De don dep, ban co the xoa record trong DB: DELETE FROM economic_events WHERE id='{FAKE_ID}';")

if __name__ == "__main__":
    database.init_db()
    run_simulation()
