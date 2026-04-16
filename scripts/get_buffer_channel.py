"""
Run this once to find your Buffer Channel ID for LinkedIn.
Usage: python scripts/get_buffer_channel.py
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BUFFER_API_KEY = os.environ.get("BUFFER_API_KEY")
if not BUFFER_API_KEY:
    raise SystemExit("BUFFER_API_KEY not set in .env")

query = """
query {
  account {
    channels {
      id
      name
      service
      serviceId
    }
  }
}
"""

resp = requests.post(
    "https://api.buffer.com",
    headers={"Authorization": f"Bearer {BUFFER_API_KEY}", "Content-Type": "application/json"},
    json={"query": query},
    timeout=15,
)
data = resp.json()

if "errors" in data:
    raise SystemExit(f"Buffer API error: {data['errors']}")

channels = data.get("data", {}).get("account", {}).get("channels", [])
if not channels:
    raise SystemExit("No channels found. Make sure your LinkedIn account is connected in Buffer.")

print("\nYour Buffer Channels:")
print("─" * 50)
for ch in channels:
    service = ch.get("service", "").upper()
    name    = ch.get("name", "unknown")
    cid     = ch.get("id", "")
    print(f"  Service : {service}")
    print(f"  Name    : {name}")
    print(f"  ID      : {cid}   ← copy this into BUFFER_CHANNEL_ID in .env")
    print()
