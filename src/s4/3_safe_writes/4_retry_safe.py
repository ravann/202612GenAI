# Step 4: no model. Agents retry: after a timeout, a dropped connection, or because the model calls the tool again.
#   A retried read is harmless. A retried create makes the same thing twice.
#   The fix: send an Idempotency-Key made from the request, so a retry gives the same key and nothing new.
# Start ServiceDesk first:  python src/servicedesk/app.py
import hashlib, json, os
import urllib.request

SERVICEDESK_URL = os.environ.get("SERVICEDESK_URL", "http://127.0.0.1:8000")
WRITE_TOKEN = "dev-engineer-token"                     # bob, role engineer: may create incidents

def servicedesk(method, path, body=None, headers=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(SERVICEDESK_URL + path, data=data, method=method,
                                     headers={"Authorization": "Bearer " + WRITE_TOKEN,
                                              "Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())

def intent_key(args):
    """Same request -> same text (sorted keys) -> same hash -> same key."""
    text = json.dumps(args, sort_keys=True)
    return "compass-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

def create_incident(incident, key=None):
    """POST /incidents: the write. Without a key, every call creates a new incident."""
    headers = {"Idempotency-Key": key} if key else None
    return servicedesk("POST", "/incidents", incident, headers)

INCIDENT = {"title": "Printer PRN-3F-EAST is offline", "description": "Nobody on floor 3 can print since 9:00.",
            "service": "printer-queue", "priority": "P3"}

if __name__ == "__main__":
    servicedesk("POST", "/_admin/reset")               # test control: start from the seed data every run
    for attempt in [1, 2]:                             # attempt 1 "timed out", so the agent sends it again
        print(f"no key,     try {attempt}: created {create_incident(INCIDENT)['id']}")
    print("two incidents for one broken printer.\n")

    servicedesk("POST", "/_admin/reset")
    for attempt in [1, 2]:
        print(f"intent key, try {attempt}: got {create_incident(INCIDENT, intent_key(INCIDENT))['id']}")
    print("the retry returned the incident made the first time.")
