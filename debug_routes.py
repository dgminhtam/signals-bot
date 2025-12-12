import requests
import json

WP_URL = "https://a-finance.info"

def dump_routes():
    print(f"🔍 Fetching API schema from {WP_URL}/wp-json/ ...")
    try:
        r = requests.get(f"{WP_URL}/wp-json/", verify=False) # Skip SSL verify just in case, though likely fine
        if r.status_code == 200:
            data = r.json()
            with open("debug_routes.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("✅ Routes saved to debug_routes.json")
            
            # Print quick summary of liveblog routes
            routes = data.get('routes', {})
            print(f"\nScanning {len(routes)} routes for 'liveblog' or 'elb'...")
            for route, info in routes.items():
                if 'liveblog' in route or 'elb' in route:
                    methods = info.get('methods', [])
                    endpoints = info.get('endpoints', [])
                    allowed_methods = []
                    for ep in endpoints:
                        allowed_methods.extend(ep.get('methods', []))
                    
                    print(f"Found: {route} | Methods: {allowed_methods}")
        else:
            print(f"❌ Failed: {r.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    dump_routes()
