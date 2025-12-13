
from app.services.economic_calendar import EconomicCalendarService

def test_week():
    svc = EconomicCalendarService()
    print("Fetching Weekly Events...")
    events = svc.fetch_events(day="this week") # "this week" parameter might need specific format handling in my service?
    # FF uses url `calendar?week=...`?
    # My service code: `url = f"{self.base_url}?day={day}"`
    # FF supports `?day=today` or `?week=this`?
    # Actually FF `?day=this` might NOT work for week.
    # I need to update service to support `week` param if I want to use it.
    # But let's check what `day=this week` does. FF might ignore it or show something else.
    # Correct FF URL for week is `calendar?week=nov17.2024` or similar? 
    # Or just `calendar`. (Default is week? No default is today or user pref).
    
    # Let's try `day=today` but since it is Saturday, maybe empty.
    # Let's try `day=nov14.2024` (Past weekday) to see data.
    # Or I should verify what my code supports.
    
    # My code currently interpolates `?day={day}`.
    # I will try to fetch a specific date known to have news.
    # Dec 12, 2024 (Thursday) likely had news.
    
    events = svc.fetch_events(day="dec12.2024")
    print(f"Found {len(events)} events for Dec 12.")
    for n in events:
        print(f"🔴 {n['time']} {n['currency']} - {n['event']}")

if __name__ == "__main__":
    test_week()
