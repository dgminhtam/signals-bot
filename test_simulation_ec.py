"""
Script giả lập quá trình sự kiện kinh tế để test Telegram Alert & AI.

Kịch bản:
1. Tạo 1 sự kiện giả "Simulation CPI Data" sắp diễn ra (còn 30 phút).
2. Chạy bot -> Kỳ vọng: Nhận Pre-Alert.
3. Cập nhật sự kiện: Đã có kết quả (Actual).
4. Chạy bot -> Kỳ vọng: Nhận Post-Alert kèm phân tích AI.

Hướng dẫn chạy:
python test_simulation_ec.py
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
    print("🚀 Bắt đầu giả lập Economic Calendar...")

    # 1. SETUP PRE-NEWS STATE
    # Tạo sự kiện ở tương lai 30 phút (để thỏa mãn < 60p Pre-Alert)
    future_time = datetime.now(tz.UTC) + timedelta(minutes=30)
    
    fake_event_pre = {
        "id": FAKE_ID,
        "title": "🔥 SIMULATION: US CPI m/m (Tin Giả Lập)",
        "currency": "USD",
        "impact": "High",
        "timestamp": future_time.isoformat(), # ISO UTC
        "forecast": "0.3%",
        "previous": "0.2%",
        "actual": "", # Chưa có
        "status": "pending" 
    }
    
    print("\n[1] Upsert Data: Sắp có tin (Pre-News)...")
    database.upsert_economic_event(fake_event_pre)
    # Reset status thủ công để đảm bảo test sạch
    # (Hàm upsert giữ status cũ nếu tồn tại, nên ta phải force update status)
    # Tuy nhiên function upsert mặc định status='pending' nếu insert mới.
    # Để chắc chắn, ta update status về pending.
    database.update_event_status(FAKE_ID, 'pending')
    
    print(">> Đang chạy check alerts...")
    svc.process_calendar_alerts()
    print("✅ Đã xử lý Pre-Alert (Kiểm tra Telegram!)")
    
    print("\n⏳ Chờ 10 giây giả lập thời gian trôi qua...")
    time.sleep(10)
    
    # 2. SETUP POST-NEWS STATE
    # Giả lập tin đã ra, có số liệu Actual cao hơn Forecast (Tốt cho USD -> Xấu cho Vàng)
    fake_event_post = fake_event_pre.copy()
    fake_event_post["actual"] = "0.5%" # Cao hơn 0.3%
    # Timestamp lùi về quá khứ 1 xíu để logic fetch không bỏ qua? 
    # Logic Post-Alert chỉ cần status != post_notified và có actual.
    
    print("\n[2] Update Data: Tin đã ra (Post-News)...")
    database.upsert_economic_event(fake_event_post)
    
    # process_calendar_alerts sẽ thấy Actual != empty và Status != post_notified
    # Nó sẽ gọi send_post_alert -> gọi AI
    print(">> Đang chạy check alerts (Kèm AI Analysis)...")
    svc.process_calendar_alerts()
    print("✅ Đã xử lý Post-Alert (Kiểm tra Telegram + AI!)")

    print("\n🎉 Hoàn tất giả lập.")
    print(f"Để dọn dẹp, bạn có thể xóa record trong DB: DELETE FROM economic_events WHERE id='{FAKE_ID}';")

if __name__ == "__main__":
    # Init DB nếu cần
    database.init_db()
    run_simulation()
