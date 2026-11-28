# Step 1: no model yet. Just the API call that a tool will wrap later.
# Start ServiceDesk first:  python src/servicedesk/app.py
import json, os
import urllib.parse, urllib.request

SERVICEDESK_URL = os.environ.get("SERVICEDESK_URL", "http://127.0.0.1:8000")
READ_TOKEN = "dev-requester-token"                     # alice, read-only

def search_incidents(service=None, status=None, priority=None):
    """GET /incidents with optional filters. Returns ServiceDesk's JSON as it came."""
    query = {}
    if service:  query["service"] = service
    if status:   query["status"] = status
    if priority: query["priority"] = priority
    url = SERVICEDESK_URL + "/incidents?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + READ_TOKEN})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())

if __name__ == "__main__":
    data = search_incidents(service="payroll-portal", status="open")
    print(f"total matched: {data['total']}")
    for incident in data["incidents"]:
        print(f"  {incident['id']}  {incident['priority']}  {incident['status']:12} {incident['title']}")
    print(f"\nOne incident, every field the API returns:\n{json.dumps(data['incidents'][0], indent=2)}")
