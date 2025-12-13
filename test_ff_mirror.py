
import requests
import json
from datetime import datetime

def test_mirror():
    url = "https://nfs.farex.io/forexfactory/calendar.json"
    print(f"Fetching {url}...")
    try:
        resp = requests.get(url, timeout=10)
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print(f"Got {len(data)} events.")
        
        # Check freshness
        if data:
            last_event = data[-1]
            print(f"Sample Event: {last_event}")
            print(f"Date: {last_event.get('date')}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_mirror()
