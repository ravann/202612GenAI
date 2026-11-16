import anthropic
from dotenv import load_dotenv
from pathlib import Path
import json, time

# The .env file is in code folder, one level up from this script
load_dotenv(Path(__file__).parent.parent / ".env")

client = anthropic.Anthropic()
MODEL = "claude-sonnet-5-5"                      # 🔎 confirm current model ID
SYSTEM = "You are Compass, an IT-operations assistant. Be concise. If you do not know, say so."

def ask(messages: list, max_tokens: int = 500, stop=None):
    resp = client.messages.create(model=MODEL, 
                                  max_tokens=max_tokens, 
                                  system=SYSTEM, 
                                  messages=messages,
                                  stop_sequences=stop or [])
    return resp

def text_of(resp):
    # thinking blocks come BEFORE text, so resp.content[0].text can raise or return the wrong block
    return "".join(b.text for b in resp.content if b.type == "text")

# USD per million tokens (input, output). Checked 2026-11-14. Prices change: re-check before every cohort. 🔎
# The Haiku 5.5 price holds for prompts up to 100K tokens; every prompt in this course is far below that.
PRICES = {"claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-5-5": (0.10, 0.50)}

def cost_usd(usage):
    price_in, price_out = PRICES[MODEL]          # a missing price is a KeyError: loud, on purpose
    return (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000

def report(resp, seconds, ttft=None):          # ttft (time to first token) exists only for streamed calls
    try:
        cost = cost_usd(resp.usage)
        shown = f"${cost:.5f}"
    except KeyError:                           # no price for MODEL: still log the billed call, with the cost unknown
        cost, shown = None, f"cost unknown: add {MODEL} to PRICES"
    first = f" | ttft {ttft:.2f}s" if ttft is not None else ""
    print(f"[{resp.usage.input_tokens} in / {resp.usage.output_tokens} out | {seconds:.2f}s{first} | {shown} | {resp.stop_reason}]")
    with open("calls.jsonl", "a") as f:       # metadata only: never the prompt text, never a key
        f.write(json.dumps({"ts": time.time(), "model": MODEL, "in": resp.usage.input_tokens,
                            "out": resp.usage.output_tokens, "seconds": round(seconds, 3),
                            "ttft": None if ttft is None else round(ttft, 3),
                            "cost_usd": cost, "stop": resp.stop_reason}) + "\n")

prompt = "List 5 common causes of VPN failure."

# print(resp.model_dump_json(indent=2))

print("with 3000 max tokens")
t0 = time.time()
resp = ask([{"role": "user", "content": prompt}], max_tokens=3000)
t1 = time.time()
report(resp, t1 - t0)  

print("with 50 max tokens")
t0 = time.time()
resp = ask([{"role": "user", "content": prompt}], max_tokens=50)
t1 = time.time()
report(resp, t1 - t0)  
