"""In-memory data store, loaded from the JSON seed files in seed/.

Nothing is saved to disk. Every start (and POST /_admin/reset) loads the same seed
data again, so every run of the course begins from the same state.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from errors import ServiceError

SEED_DIR = Path(__file__).parent / "seed"

INCIDENT_SUMMARY_FIELDS = ["id", "title", "service", "priority", "status", "assignee", "asset_ids",
                           "created_at", "updated_at"]
RUNBOOK_SUMMARY_FIELDS = ["id", "title", "classification", "service", "owner", "updated_at"]


def now_text():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_seed(name):
    with open(SEED_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def pick_fields(record, fields):
    result = {}
    for field in fields:
        result[field] = record[field]
    return result


def not_found(kind, item_id, hint):
    return ServiceError(404, "not_found", f"No {kind} {item_id}", hint)


class Store:
    def __init__(self):
        self.lock = threading.Lock()     # requests run in parallel threads; one change at a time
        self.reset()

    def reset(self):
        with self.lock:
            self.incidents = {}
            for incident in read_seed("incidents.json"):
                self.incidents[incident["id"]] = incident

            self.assets = {}
            for asset in read_seed("assets.json"):
                self.assets[asset["id"]] = asset

            self.changes = {}
            for change in read_seed("changes.json"):
                self.changes[change["id"]] = change

            self.runbooks = {}
            for entry in read_seed("runbooks.json"):
                runbook = pick_fields(entry, RUNBOOK_SUMMARY_FIELDS)
                runbook["body"] = (SEED_DIR / "runbooks" / entry["file"]).read_text(encoding="utf-8")
                self.runbooks[runbook["id"]] = runbook

            self.idempotency = {}        # "user operation key" -> the request and the ID it created
            self.next_incident_number = len(self.incidents) + 1
            self.next_change_number = len(self.changes) + 1

    def counts(self):
        return {"incidents": len(self.incidents), "assets": len(self.assets),
                "changes": len(self.changes), "runbooks": len(self.runbooks)}

    # ---------- Idempotency ----------

    def find_replay(self, username, operation, key, request):
        """Return the ID created earlier with this key, or None if the key is new."""
        if key is None:
            return None
        saved = self.idempotency.get(username + " " + operation + " " + key)
        if saved is None:
            return None
        if saved["request"] != request:
            raise ServiceError(422, "idempotency_key_reused",
                               f"Idempotency-Key {key} was already used for a different request",
                               "Send a new key for a new request; reuse a key only to retry the same request")
        return saved["created_id"]

    def remember(self, username, operation, key, request, created_id):
        if key is not None:
            self.idempotency[username + " " + operation + " " + key] = {"request": request,
                                                                        "created_id": created_id}

    def check_assets_exist(self, asset_ids):
        for asset_id in asset_ids:
            if asset_id not in self.assets:
                raise ServiceError(422, "unknown_asset", f"No asset {asset_id}",
                                   "Use GET /assets?q=<name> to find valid asset IDs")

    # ---------- Incidents ----------

    def search_incidents(self, status, priority, service, asset_id, limit):
        with self.lock:
            matches = []
            for incident in reversed(self.incidents.values()):     # the newest incident was added last
                if status is None and incident["status"] == "closed":
                    continue                                       # closed ones only when asked for
                if status is not None and incident["status"] != status:
                    continue
                if priority is not None and incident["priority"] != priority:
                    continue
                if service is not None and incident["service"] != service:
                    continue
                if asset_id is not None and asset_id.lower() not in incident["asset_ids"]:
                    continue
                matches.append(pick_fields(incident, INCIDENT_SUMMARY_FIELDS))
            return {"total": len(matches), "returned": len(matches[:limit]), "incidents": matches[:limit]}

    def get_incident(self, incident_id):
        with self.lock:
            incident = self.incidents.get(incident_id.upper())
            if incident is None:
                raise not_found("incident", incident_id, "Use GET /incidents to find valid incident IDs")
            return incident

    def create_incident(self, username, request, idempotency_key):
        """Returns (incident, replayed). replayed is True when the key was seen before."""
        with self.lock:
            earlier_id = self.find_replay(username, "create_incident", idempotency_key, request)
            if earlier_id is not None:
                return self.incidents[earlier_id], True
            self.check_assets_exist(request["asset_ids"])
            incident_id = f"INC-{self.next_incident_number:04d}"
            self.next_incident_number = self.next_incident_number + 1
            now = now_text()
            incident = {"id": incident_id, "title": request["title"], "description": request["description"],
                        "service": request["service"], "priority": request["priority"], "status": "open",
                        "assignee": None, "reporter": username, "asset_ids": request["asset_ids"],
                        "created_at": now, "updated_at": now, "comments": []}
            self.incidents[incident_id] = incident
            self.remember(username, "create_incident", idempotency_key, request, incident_id)
            return incident, False

    def update_incident(self, incident_id, status, assignee):
        with self.lock:
            incident = self.incidents.get(incident_id.upper())
            if incident is None:
                raise not_found("incident", incident_id, "Use GET /incidents to find valid incident IDs")
            if status is not None:
                incident["status"] = status
            if assignee is not None:
                incident["assignee"] = assignee
            incident["updated_at"] = now_text()
            return incident

    def add_comment(self, incident_id, username, body):
        with self.lock:
            incident = self.incidents.get(incident_id.upper())
            if incident is None:
                raise not_found("incident", incident_id, "Use GET /incidents to find valid incident IDs")
            comment = {"id": len(incident["comments"]) + 1, "author": username,
                       "created_at": now_text(), "body": body}
            incident["comments"].append(comment)
            incident["updated_at"] = comment["created_at"]
            return comment

    # ---------- Assets ----------

    def list_assets(self, q, service, asset_type, limit):
        with self.lock:
            matches = []
            for asset_id in sorted(self.assets):
                asset = self.assets[asset_id]
                if q is not None:
                    text = (asset["id"] + " " + asset["name"]).lower()
                    if q.lower() not in text:
                        continue
                if service is not None and asset["service"] != service:
                    continue
                if asset_type is not None and asset["type"] != asset_type:
                    continue
                matches.append(asset)
            return {"total": len(matches), "returned": len(matches[:limit]), "assets": matches[:limit]}

    def get_asset(self, asset_id):
        with self.lock:
            asset = self.assets.get(asset_id.lower())
            if asset is None:
                raise not_found("asset", asset_id, "Use GET /assets?q=<name> to find valid asset IDs")
            return asset

    def direct_links(self, asset_id, direction):
        """IDs one step away. direction "up": what it depends on. "down": what depends on it."""
        if direction == "up":
            return self.assets[asset_id]["depends_on"]
        users = []
        for other in self.assets.values():
            if asset_id in other["depends_on"]:
                users.append(other["id"])
        return users

    def walk(self, start_id, direction):
        """Follow the dependency chain one step at a time (breadth-first)."""
        found = []
        seen = [start_id]
        current = [start_id]
        depth = 0
        while current:
            depth = depth + 1
            following = []
            for asset_id in current:
                for linked_id in self.direct_links(asset_id, direction):
                    if linked_id in seen:
                        continue
                    seen.append(linked_id)
                    linked = self.assets[linked_id]
                    found.append({"id": linked_id, "name": linked["name"], "type": linked["type"],
                                  "service": linked["service"], "depth": depth})
                    following.append(linked_id)
            current = following
        return found

    def get_dependencies(self, asset_id):
        with self.lock:
            asset = self.assets.get(asset_id.lower())
            if asset is None:
                raise not_found("asset", asset_id, "Use GET /assets?q=<name> to find valid asset IDs")
            used_by = self.walk(asset["id"], "down")
            impacted = []
            if asset["service"] != "shared-infra":
                impacted.append(asset["service"])
            for item in used_by:
                if item["service"] != "shared-infra" and item["service"] not in impacted:
                    impacted.append(item["service"])
            return {"asset_id": asset["id"], "depends_on": self.walk(asset["id"], "up"),
                    "used_by": used_by, "impacted_services": impacted}

    # ---------- Change requests ----------

    def list_changes(self, status, service, limit):
        with self.lock:
            matches = []
            for change in reversed(self.changes.values()):
                if status is not None and change["status"] != status:
                    continue
                if service is not None and change["service"] != service:
                    continue
                matches.append(change)
            return {"total": len(matches), "returned": len(matches[:limit]), "changes": matches[:limit]}

    def get_change(self, change_id):
        with self.lock:
            change = self.changes.get(change_id.upper())
            if change is None:
                raise not_found("change request", change_id, "Use GET /changes to find valid change IDs")
            return change

    def create_change(self, username, request, idempotency_key):
        """Returns (change, replayed). replayed is True when the key was seen before."""
        with self.lock:
            earlier_id = self.find_replay(username, "create_change", idempotency_key, request)
            if earlier_id is not None:
                return self.changes[earlier_id], True
            self.check_assets_exist(request["asset_ids"])
            related = request["related_incident"]
            if related is not None:
                related = related.upper()
                if related not in self.incidents:
                    raise ServiceError(422, "unknown_incident", f"No incident {request['related_incident']}",
                                       "Use GET /incidents to find valid incident IDs, or leave related_incident out")
            change_id = f"CHG-{self.next_change_number:04d}"
            self.next_change_number = self.next_change_number + 1
            change = {"id": change_id, "title": request["title"], "description": request["description"],
                      "service": request["service"], "asset_ids": request["asset_ids"], "risk": request["risk"],
                      "related_incident": related, "rollback_plan": request["rollback_plan"],
                      "planned_start": request["planned_start"], "status": "pending_approval",
                      "requested_by": username, "created_at": now_text(),
                      "approved_by": None, "approved_at": None}
            self.changes[change_id] = change
            self.remember(username, "create_change", idempotency_key, request, change_id)
            return change, False

    def approve_change(self, change_id, username):
        with self.lock:
            change = self.changes.get(change_id.upper())
            if change is None:
                raise not_found("change request", change_id, "Use GET /changes to find valid change IDs")
            if change["status"] != "pending_approval":
                raise ServiceError(409, "invalid_state",
                                   f"Change {change['id']} is {change['status']}, not pending_approval",
                                   "Only a change in pending_approval can be approved")
            change["status"] = "approved"
            change["approved_by"] = username
            change["approved_at"] = now_text()
            return change

    # ---------- Runbooks ----------

    def list_runbooks(self, include_restricted, service, classification, q):
        with self.lock:
            matches = []
            for runbook in self.runbooks.values():
                if runbook["classification"] == "restricted" and not include_restricted:
                    continue                       # the caller may not even see that it exists
                if service is not None and runbook["service"] != service:
                    continue
                if classification is not None and runbook["classification"] != classification:
                    continue
                if q is not None:
                    text = (runbook["title"] + " " + runbook["body"]).lower()
                    if q.lower() not in text:
                        continue
                matches.append(pick_fields(runbook, RUNBOOK_SUMMARY_FIELDS))
            return {"total": len(matches), "runbooks": matches}

    def get_runbook(self, runbook_id):
        with self.lock:
            runbook = self.runbooks.get(runbook_id.upper())
            if runbook is None:
                raise not_found("runbook", runbook_id, "Use GET /runbooks to list the runbooks you may read")
            return runbook


STORE = Store()
