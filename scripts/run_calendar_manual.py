import sys
import os

# Add project root to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.economic_calendar import EconomicCalendarService

def run_manual():
    print("🚀 Starting Manual Economic Calendar Update...")
    print("   This will sync schedule from JSON and fetch Real-time Actuals from HTML.")
    
    try:
        service = EconomicCalendarService()
        service.process_calendar_alerts()
        print("✅ Manual update process finished successfully.")
    except Exception as e:
        print(f"❌ Error during manual update: {e}")

if __name__ == "__main__":
    run_manual()
