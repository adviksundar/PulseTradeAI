import requests

URL = "http://127.0.0.1:8000/api/agent-status"
try:
    r = requests.get(URL, timeout=5)
    r.raise_for_status()
    print(r.text)
except Exception as e:
    print("Failed to fetch agent-status:", e)
