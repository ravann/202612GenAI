# Step 2: step 1 + a model that calls search_incidents through a WEAK tool definition.
# Watch what the model has to guess, and what it gets back when it guesses wrong.
import json, os, sys
import urllib.error, urllib.parse, urllib.request
from dataclasses import replace
from pathlib import Path
from dotenv import find_dotenv, load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))  # reuse src/s4/model_adapter.py and model.toml
from model_adapter import ModelAdapter, ModelConfig

CYAN, GREEN, RESET = "\033[36m", "\033[32m", "\033[0m"
load_dotenv(find_dotenv())

SERVICEDESK_URL = os.environ.get("SERVICEDESK_URL", "http://127.0.0.1:8000")
READ_TOKEN = "dev-requester-token"

# ---------- Step 1's API call (unchanged, except it now takes the model's arguments) ----------

def search_incidents(args):
    url = SERVICEDESK_URL + "/incidents?" + urllib.parse.urlencode(args)
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + READ_TOKEN})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())                 # every field of every incident, as it came
    except urllib.error.HTTPError as e:
        return str(e)                                          # "HTTP Error 422: ..." : what? why? what next?

# ---------- NEW: the tool definition, i.e. everything the model knows about search_incidents ----------

WEAK_TOOL = {
    "name": "get_data",                                        # data about what?
    "description": "Gets incidents.",                          # no filters explained, no limits, no order
    "input_schema": {"type": "object",
                     "properties": {"service": {"type": "string"},      # which values are valid? the model guesses
                                    "status": {"type": "string"},
                                    "priority": {"type": "string"}}}}

# ---------- NEW: the model call and the tool loop ----------

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
    ask_with_tool(QUESTION, WEAK_TOOL, search_incidents)
