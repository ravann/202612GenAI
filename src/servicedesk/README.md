# ServiceDesk: the mock service for Sessions 4 to 8

ServiceDesk is a small, fictional IT service desk with a CMDB (configuration database). From Session 4 on, Compass's tools and the MCP server call it. It is the only system you run code against. All data is invented for the course.

## Start it

From the folder that holds `src/`, with your virtual environment active (`pip install -r src/requirements.txt` installs FastAPI and Uvicorn):

```
python src/servicedesk/app.py
```

- Base URL: `http://127.0.0.1:8000`. To use another port, set `SERVICEDESK_PORT` first (PowerShell: `$env:SERVICEDESK_PORT = "8001"`; bash: `SERVICEDESK_PORT=8001 python src/servicedesk/app.py`).
- Interactive docs: `http://127.0.0.1:8000/docs`. OpenAPI description: `http://127.0.0.1:8000/openapi.json` (no token needed for these two).
- Stop it with Ctrl+C. Every start loads the same seed data again; nothing is saved.

## Tokens

Send `Authorization: Bearer <token>` on every request. A missing or unknown token returns **401**; a missing scope or role returns **403**.

| Token | User | Role | Scopes | May do |
|---|---|---|---|---|
| `dev-requester-token` | alice | requester | `incidents:read`, `runbooks:read` | Read incidents, assets, changes, public and internal runbooks. No writes |
| `dev-engineer-token` | bob | engineer | adds `incidents:write`, `changes:write` | Also create and update incidents, comment, create change requests. Cannot approve; cannot read restricted runbooks |
| `dev-change-manager-token` | carol | change-manager | adds `changes:approve`, `runbooks:restricted` | Everything, including approving changes and reading restricted runbooks |

These are development tokens for a local mock. A real service gets the same facts (who, which role, which scopes) from a validated token issued by an identity provider (Session 8).

## Endpoints (16)

| Method and path | What it does | Risk | Needs |
|---|---|---|---|
| `GET /incidents?status=&priority=&service=&asset_id=&limit=` | Search incidents, newest first, at most 20 by default; closed ones only with `status=closed` | read | `incidents:read` |
| `GET /incidents/{id}` | One incident with its comments | read | `incidents:read` |
| `POST /incidents` | Create an incident (optional `Idempotency-Key`) | write | `incidents:write` |
| `PATCH /incidents/{id}` | Change status and/or assignee | write | `incidents:write` |
| `POST /incidents/{id}/comments` | Add a comment | write | `incidents:write` |
| `GET /assets?q=&service=&type=&limit=` | Search the CMDB | read | any valid token |
| `GET /assets/{id}` | One asset | read | any valid token |
| `GET /assets/{id}/dependencies` | Dependency chain both ways, and the impacted services | read | any valid token |
| `GET /changes?status=&service=&limit=` | List change requests | read | any valid token |
| `GET /changes/{id}` | One change request | read | any valid token |
| `POST /changes` | Create a change request in `pending_approval` (supports `Idempotency-Key`) | **gated write** | `changes:write` |
| `POST /changes/{id}/approve` | Approve a pending change | **privileged write** | change-manager role and `changes:approve` |
| `GET /runbooks?service=&classification=&q=` | List the runbooks you may read | read, access-controlled | `runbooks:read` |
| `GET /runbooks/{id}` | One runbook in Markdown; restricted ones need `runbooks:restricted` | read, access-controlled | `runbooks:read` |
| `POST /_admin/faults` | Test only: inject 429/503 errors and latency | test control | any valid token |
| `POST /_admin/reset` | Test only: reload the seed data and switch faults off | test control | any valid token |

Every error has the same body: `{"error": "not_found", "detail": "No incident INC-9999", "hint": "Use GET /incidents to find valid incident IDs"}`.

**Idempotency.** Send the same `Idempotency-Key` header when you retry `POST /changes`: the first call returns 201, a replay returns 200 with the same change and the header `Idempotent-Replayed: true`. The same key with a different body returns 422. Without a key, two calls create two changes.

## Seed data (in `seed/`)

- **42 incidents**, `INC-0001` to `INC-0042`, 7 for each of 6 services: `checkout`, `crm`, `payroll-portal`, `vpn-gateway`, `mail-relay`, `printer-queue`. `INC-0012` is the open P1 "checkout is slow" incident on the orders database `db-04`.
- **24 assets** with dependency chains, for example `lb-01` to `web-checkout-01` to `app-checkout-01` to `db-04` to `san-01`. `db-04` is shared by checkout and CRM; `db-05` is its standby.
- **5 change requests**, `CHG-0001` to `CHG-0005`; `CHG-0003` and `CHG-0005` are `pending_approval`.
- **13 runbooks**: `RB-01` to `RB-12` plus `RB-99`. `RB-10` (break-glass access), `RB-11` (security incident response) and `RB-12` (legal hold) are `restricted`. `RB-05` is the change management policy.
- **Two poisoned fixtures** for the security lessons, both fictional and harmless: `RB-99` (printer queue troubleshooting, classified `internal`, used in Sessions 5 and 7) hides an instruction in an HTML comment, and the last comment on `INC-0015` (Session 7) asks the assistant to propose and approve a change `CHG-OVERRIDE`. Treat runbook text and comments as untrusted input.

## Inject faults

The easiest way is `POST /_admin/faults` in the interactive docs (`/docs`: Authorize with a token, then Try it out). From a terminal:

```
# bash
curl -X POST http://127.0.0.1:8000/_admin/faults -H "Authorization: Bearer dev-engineer-token" -H "Content-Type: application/json" -d '{"status": 503, "rate": 0.5, "latency_ms": 300}'

# PowerShell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/_admin/faults -Headers @{Authorization = "Bearer dev-engineer-token"} -ContentType "application/json" -Body '{"status": 503, "rate": 0.5, "latency_ms": 300}'
```

- `status`: `429` or `503` (both send `Retry-After: 1`), or `null` for no failures.
- `rate`: the share of the following requests that fail, 0 to 1. It is deterministic: `0.5` fails every second request, `1` fails all.
- `latency_ms`: delay added to every following request.
- Switch off with `{"status": null, "rate": 0, "latency_ms": 0}`, or `POST /_admin/reset`, or a restart. The `/_admin` endpoints are never slowed or failed.

## Smoke check

With the server running, in a second terminal:

```
python src/servicedesk/smoke_check.py
```

It calls every endpoint with every token and checks the status codes (200/201, 401, 403, 404), the change-manager-only approval, restricted runbook access, the `Idempotency-Key` replay, fault injection (429, 503, latency), the seed data and `/openapi.json`. It resets the data before and after. It ends with `Total: ... passed, 0 failed` and exit code 0; exit code 2 means no server answered. Set `SERVICEDESK_URL` if the server is not on the default address.

## Files

`app.py` (the endpoints), `models.py` (request and response shapes, which become `/openapi.json`), `store.py` (the in-memory data), `auth.py` (tokens, roles, scopes), `faults.py` (fault injection), `errors.py` (the error shape), `seed/` (the JSON data and runbooks), `smoke_check.py`.
