import time
import requests

BASE = "http://127.0.0.1:8000"

# Add a temporary ticker to trigger bootstrap
try:
    r = requests.post(BASE + "/api/watchlist",
                      json={"tickers": ["GOOG"]}, timeout=10)
    print("watchlist POST status:", r.status_code)
    try:
        print(r.json())
    except Exception as e:
        print(r.text)
except Exception as e:
    print("Failed to POST watchlist:", e)

# Poll agent-status for up to 60s
for i in range(30):
    try:
        s = requests.get(BASE + "/api/agent-status", timeout=5).json()
    except Exception as e:
        print("agent-status fetch failed:", e)
        time.sleep(2)
        continue
    pe = s.get("processed_events")
    logs = s.get("logs") or []
    print(f"poll {i}: processed_events={pe}, recent_logs={len(logs)}")
    if pe and pe > 0:
        print("Agent processed events; returning snapshot and logs.")
        snap = requests.get(BASE + "/api/snapshot", timeout=5)
        print("snapshot status:", snap.status_code)
        print(snap.text[:2000])
        if logs:
            print("recent logs (truncated):")
            for entry in logs[-10:]:
                print(entry)
        break
    time.sleep(2)
else:
    print("No events processed within timeout.")
