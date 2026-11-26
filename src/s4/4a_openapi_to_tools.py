import json, os, sys
import urllib.error, urllib.request
from pathlib import Path

# Generate draft tools from ServiceDesk's OpenAPI description: one draft per operation, no model call.
# Names come from operationId, descriptions from the summary and the docstring, schemas from the parameters
# and the request body. The drafts mirror the API, so they still need curating (4b_curate.py).

HERE = Path(__file__).parent
SERVICEDESK_URL = os.environ.get("SERVICEDESK_URL", "http://127.0.0.1:8000")
SHIPPED = HERE / "generated_tools.json"                # the pre-generated copy: the fallback, never overwritten here
OUT = HERE / "reports" / "generated_tools.json"        # what this run generates

def load_openapi():
    with urllib.request.urlopen(SERVICEDESK_URL + "/openapi.json", timeout=10) as response:
        return json.loads(response.read())

def body_schema(operation, components):
    """The request body's schema, looked up in components, or None if the operation has no body."""
    if "requestBody" not in operation:
        return None
    ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]   # "#/components/schemas/NewChange"
    return components[ref.split("/")[-1]]

def draft_tool(method, path, operation, components):
    """One draft tool for one operation. Every parameter and body field becomes a property, as the API has it."""
    properties = {}
    required = []
    for param in operation.get("parameters", []):      # path, query and header parameters
        prop = dict(param["schema"])
        prop["description"] = param.get("description", "")
        properties[param["name"]] = prop
        if param.get("required"):
            required.append(param["name"])
    body = body_schema(operation, components)
    if body is not None:
        for name, prop in body["properties"].items():
            properties[name] = prop
        for name in body.get("required", []):
            required.append(name)
    return {"name": operation["operationId"],
            "description": operation["summary"] + ". " + operation.get("description", ""),
            "input_schema": {"type": "object", "properties": properties, "required": required},
            "x-http": method.upper() + " " + path,       # for the curation table; not sent to a model
            "x-risk": operation.get("x-risk", "")}

def generate(openapi):
    drafts = []
    for path, operations in openapi["paths"].items():
        for method, operation in operations.items():
            drafts.append(draft_tool(method, path, operation, openapi["components"]["schemas"]))
    return drafts

if __name__ == "__main__":
    try:
        openapi = load_openapi()
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:   # not running, too slow (10 s), or dropped
        print(f"ServiceDesk did not answer at {SERVICEDESK_URL} ({e}).")
        print(f"Start it with: python src/servicedesk/app.py, or use the pre-generated {SHIPPED.name}.")
        sys.exit(2)
    drafts = generate(openapi)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(drafts, indent=2) + "\n", encoding="utf-8")
    print(f"{len(drafts)} draft tools from {openapi['info']['title']} {openapi['info']['version']}:")
    for d in drafts:
        print(f"  {d['name']:23} {d['x-http']:39} {d['x-risk']:17} {len(d['input_schema']['properties'])} properties")
    print("saved", OUT)
    if SHIPPED.exists():
        same = json.loads(SHIPPED.read_text(encoding="utf-8")) == drafts
        print(f"same as the pre-generated {SHIPPED.name}: {same}")
