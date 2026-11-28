# Step 2: step 1 + a model that can call assign_incident. No checks at all.
# The user asks for something reasonable. Count how many records change before anyone can say "wait".
import json, os, sys
import urllib.parse, urllib.request
from dataclasses import replace
from pathlib import Path
from dotenv import find_dotenv, load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))  # reuse src/s4/model_adapter.py and model.toml
from model_adapter import ModelAdapter, ModelConfig

CYAN, GREEN, YELLOW, RESET = "\033[36m", "\033[32m", "\033[33m", "\033[0m"
load_dotenv(find_dotenv())

SERVICEDESK_URL = os.environ.get("SERVICEDESK_URL", "http://127.0.0.1:8000")
WRITE_TOKEN = "dev-engineer-token"

def servicedesk(method, path, body=None, query=None):
    url = SERVICEDESK_URL + path + ("?" + urllib.parse.urlencode(query) if query else "")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Authorization": "Bearer " + WRITE_TOKEN,
                                              "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())

# ---------- Two tools: one read, one write ----------

TOOLS = [
    {"name": "search_incidents",
     "description": "Search incidents by service. Returns id, title, status and assignee of each.",
     "input_schema": {"type": "object",
                      "properties": {"service": {"type": "string",
                                                 "enum": ["checkout", "crm", "payroll-portal", "vpn-gateway",
                                                          "mail-relay", "printer-queue"]}},
                      "required": ["service"], "additionalProperties": False}},
    {"name": "assign_incident",
     "description": "Assign one incident to an engineer.",
     "input_schema": {"type": "object",
                      "properties": {"incident_id": {"type": "string", "pattern": "^INC-[0-9]{4}$"},
                                     "assignee": {"type": "string", "enum": ["bob", "dave", "erin"]}},
                      "required": ["incident_id", "assignee"], "additionalProperties": False}},
]

def search_incidents(args):
    data = servicedesk("GET", "/incidents", query={"service": args["service"]})
    return [{k: i[k] for k in ["id", "title", "status", "assignee"]} for i in data["incidents"]]

def assign_incident(args):
    i = servicedesk("PATCH", "/incidents/" + args["incident_id"], {"assignee": args["assignee"]})
    return {"id": i["id"], "assignee": i["assignee"]}

FUNCTIONS = {"search_incidents": search_incidents, "assign_incident": assign_incident}

def dispatch(name, args):
    """Runs whatever the model asks for. This is the line step 3 changes."""
    return FUNCTIONS[name](args)

# ---------- The tool loop (as in 2_tool_design) ----------

def ask_with_tools(question, max_steps=6):
    config = ModelConfig.load(Path(__file__).parent.parent / "model.toml")
    model = ModelAdapter(replace(config, system="You are Compass, an IT-operations assistant. Be concise."))
    messages = [{"role": "user", "content": question}]
    for step in range(1, max_steps + 1):
        resp = model.ask(messages, tools=TOOLS)
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            print(f"{GREEN}ANSWER: {model.text_of(resp)}{RESET}")
            return
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                print(f"{YELLOW}  step {step} -> {block.name}({json.dumps(block.input)}){RESET}")
                out = dispatch(block.name, block.input)
                print(f"           <- {json.dumps(out, indent=2)}")
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out)})
        messages.append({"role": "user", "content": results})

def assignees(service):
    return {i["id"]: i["assignee"] for i in servicedesk("GET", "/incidents", query={"service": service})["incidents"]}

QUESTION = "Give all the printer incidents to dave."

if __name__ == "__main__":
    servicedesk("POST", "/_admin/reset")
    before = assignees("printer-queue")
    print(f"{CYAN}USER: {QUESTION}{RESET}")
    ask_with_tools(QUESTION)
    after = assignees("printer-queue")
    changed = [f"{i}: {before[i]} -> {after[i]}" for i in after if before.get(i) != after[i]]
    print(f"\n{CYAN}{len(changed)} records changed, and no person saw a single call first:{RESET}")
    for line in changed:
        print("  ", line)
