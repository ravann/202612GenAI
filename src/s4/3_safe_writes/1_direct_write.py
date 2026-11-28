# Step 1: no model yet. One write, done by hand, to see what makes it different from a read.
#   A read can run 100 times and nothing changes. A write changes ServiceDesk for everyone, at once.
# Start ServiceDesk first:  python src/servicedesk/app.py
import json, os
import urllib.request

SERVICEDESK_URL = os.environ.get("SERVICEDESK_URL", "http://127.0.0.1:8000")
WRITE_TOKEN = "dev-engineer-token"                     # bob, role engineer: may update incidents

def servicedesk(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(SERVICEDESK_URL + path, data=data, method=method,
                                     headers={"Authorization": "Bearer " + WRITE_TOKEN,
                                              "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())

def assign_incident(incident_id, assignee):
    """PATCH /incidents/{id}: the write. It returns only after the change is stored."""
    return servicedesk("PATCH", "/incidents/" + incident_id, {"assignee": assignee})

if __name__ == "__main__":
    servicedesk("POST", "/_admin/reset")               # test control: start from the seed data every run
    before = servicedesk("GET", "/incidents/INC-0030")
    print(f"before: INC-0030 assignee={before['assignee']}  status={before['status']}  ({before['title']})")
    assign_incident("INC-0030", "dave")
    after = servicedesk("GET", "/incidents/INC-0030")
    print(f"after:  INC-0030 assignee={after['assignee']}  status={after['status']}")
    print("\nerin was working on this. Now it is dave's, and no one asked erin, or anyone else.")
