import requests
import json

URL = "http://127.0.0.1:8000/api/snapshot"
try:
    r = requests.get(URL, timeout=10)
    r.raise_for_status()
    data = r.json()
    insights = data.get("insights", [])
    print(f"insights count: {len(insights)}")
    for i, ins in enumerate(insights[:10]):
        print(json.dumps(ins, indent=2, default=str))
except Exception as e:
    print("Failed to fetch snapshot:", e)
