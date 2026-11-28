# Step 3: step 2 + a STRONG tool definition. Same question, same model, same loop.
# Only three things change: what the model is told, what the code checks, and what comes back.
import json, os, sys
import urllib.error, urllib.parse, urllib.request
from dataclasses import replace
from pathlib import Path
import jsonschema
from dotenv import find_dotenv, load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))  # reuse src/s4/model_adapter.py and model.toml
from model_adapter import ModelAdapter, ModelConfig

CYAN, GREEN, RESET = "\033[36m", "\033[32m", "\033[0m"
load_dotenv(find_dotenv())

SERVICEDESK_URL = os.environ.get("SERVICEDESK_URL", "http://127.0.0.1:8000")
READ_TOKEN = "dev-requester-token"

# ---------- CHANGED 1: the tool definition. The model no longer has to guess ----------

SERVICES = ["checkout", "crm", "payroll-portal", "vpn-gateway", "mail-relay", "printer-queue"]

STRONG_TOOL = {
    "name": "search_incidents",                                # says what it does
    "description": "Search ServiceDesk incidents by service, status and priority. "
                   "Returns at most `limit` incidents (default 10), newest first, plus the total that matched. "
                   "Closed incidents are left out unless status is 'closed'.",
    "input_schema": {"type": "object",
                     "properties": {
                         "service": {"type": "string", "enum": SERVICES, "description": "Business service. Leave out for all."},
                         "status": {"type": "string", "enum": ["open", "in_progress", "resolved", "closed"]},
                         "priority": {"type": "string", "enum": ["P1", "P2", "P3", "P4"],
                                      "description": "P1 is the most urgent, P4 the least."},
                         "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                     "additionalProperties": False}}               # an unknown argument is an error, not ignored

def error(code, message, hint):
    """One error shape: what went wrong, and what to do next."""
    return_message = {"ok": False, "error": {"code": code, "message": message, "hint": hint}}
    return return_message

# ---------- CHANGED 2 and 3: check the arguments in code, return only what a decision needs ----------

def search_incidents(args):
    try:
        jsonschema.validate(args, STRONG_TOOL["input_schema"])  # the schema the model saw, enforced by your code
    except jsonschema.ValidationError as e:
        print("Invalid argument caught during schema validation to search_incidents:", e.message)
        return error("invalid_arguments", e.message, "Fix this argument and call search_incidents again")
    query = {"limit": args.get("limit", 10), **{k: v for k, v in args.items() if k != "limit"}}
    url = SERVICEDESK_URL + "/incidents?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + READ_TOKEN})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())                            # ServiceDesk errors carry error, detail, hint
        return error(body["error"], body["detail"], body["hint"])
    fields = ["id", "title", "priority", "status", "assignee"]  # fewer fields: less to read, pay for, leak
    incidents = [{f: incident[f] for f in fields} for incident in data["incidents"]]
    return {"ok": True, "total": data["total"], "returned": len(incidents), "incidents": incidents}

# ---------- Step 2's model call and tool loop (unchanged) ----------

def ask_with_tool(question, tool, function, max_steps=5):
    config = ModelConfig.load(Path(__file__).parent.parent / "model.toml")
    model = ModelAdapter(replace(config, system="You are Compass, an IT-operations assistant. Be concise."))
    messages = [{"role": "user", "content": question}]
    tokens_in = tokens_out = 0
    for step in range(1, max_steps + 1):
        resp = model.ask(messages, tools=[tool])
        tokens_in += resp.usage.input_tokens
        tokens_out += resp.usage.output_tokens
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            print(f"{GREEN}ANSWER: {model.text_of(resp)}{RESET}")
            break
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                print(f"{GREEN}  step {step} -> {block.name}({json.dumps(block.input)}){RESET}")
                out = function(block.input)
                text = json.dumps(out)
                print(f"           <- {len(text)} characters: {text[:120]}...")
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": text})
        messages.append({"role": "user", "content": results})
    price_in, price_out = config.prices[config.model]          # USD per million tokens
    cost = (tokens_in * price_in + tokens_out * price_out) / 1_000_000
    print(f"{CYAN}[steps {step} | {tokens_in} in / {tokens_out} out | ${cost:.4f}]{RESET}")

QUESTION = "Are there any urgent incidents open for the payroll portal?"

if __name__ == "__main__":
    print(f"{CYAN}USER: {QUESTION}{RESET}")
    ask_with_tool(QUESTION, STRONG_TOOL, search_incidents)

    print(f"\n{CYAN}And when an argument is still wrong, the error says what to do next:{RESET}")
    print("  ", search_incidents({"priority": "urgent"}))
