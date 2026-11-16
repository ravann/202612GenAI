import anthropic
from dotenv import load_dotenv
from pathlib import Path
import json, os, sys, time

# The .env file is in code folder, one level up from this script
load_dotenv(Path(__file__).parent.parent / ".env")

client = anthropic.Anthropic(timeout=30, max_retries=2)      # both numbers are visible and yours to change
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

CYAN, RESET = "\033[36m", "\033[0m"      # ANSI escape codes; work in most terminals

def ask_stream(messages):
    started, ttft = time.perf_counter(), None
    with client.messages.stream(model=MODEL, max_tokens=2000, system=SYSTEM, messages=messages) as stream:
        for chunk in stream.text_stream:
            if ttft is None:
                ttft = time.perf_counter() - started      # what the user feels as "it started"
            print(f"{CYAN}{chunk}{RESET}", end="", flush=True)   # reset per chunk so an interrupt can't leave the terminal tinted
        resp = stream.get_final_message()                 # usage exists only once the stream ends
    return resp, ttft

def safe_chat_turn(history):
    try:
        return ask_stream(history)
    except anthropic.APIStatusError as e:                     # the server answered with an error status
        body = e.body if isinstance(e.body, dict) else {}
        err = body.get("error", body)
        kind = err.get("type", "") if isinstance(err, dict) else ""
        if e.status_code == 200:                              # an error event mid-stream arrives on an HTTP 200
            transient = kind in ("overloaded_error", "api_error", "rate_limit_error")
        else:
            transient = e.status_code in (408, 409, 429) or e.status_code >= 500
        hints = {401: "check ANTHROPIC_API_KEY", 403: "key lacks permission", 404: "check the model ID",
                 413: "request too large, shorten the history"}
        advice = "transient, retries used up" if transient else hints.get(e.status_code, "fix the request, do not retry")
        print(f"\n[error {f'{e.status_code} {kind}'.strip()}: {advice}]")
    except anthropic.APIConnectionError:                      # includes timeouts
        print("\n[connection or timeout error, retries used up]")
    except KeyboardInterrupt:                                 # Ctrl+C mid-stream: drop the partial answer
        print(f"{RESET}\n[interrupted]")
    return None

def chat():
    history = []
    while (True):
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if (q in ["exit", "quit", "q"]): 
            break
        if(q == ""): 
            continue
        history.append({"role": "user", "content": q})
        started = time.perf_counter()
        result = safe_chat_turn(history)
        if result is None:
            history.pop()                                     # keep user/assistant turns alternating
            continue
        resp, ttft = result
        seconds = time.perf_counter() - started
        text = text_of(resp)
        if not text:                                          # e.g. refusal or thinking-only response
            print(f"\n[empty response, stop_reason={resp.stop_reason}; not saved to history]")
            history.pop()
            continue
        print()                                               # the stream already printed the answer: just end the line
        if resp.stop_reason == "max_tokens":
            print("[answer truncated: max_tokens reached]")
        elif resp.stop_reason == "refusal":
            print("[the model declined to answer]")
        try:
            report(resp, seconds, ttft)
        except (KeyError, OSError) as e:                      # a logging or pricing problem must not kill the chat
            print(f"[usage logging failed: {e!r}]")
        history.append({"role": "assistant", "content": text})   # state is the application's job


if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):                    # otherwise the first request fails with a TypeError
        sys.exit("ANTHROPIC_API_KEY is not set (expected in code/.env)")
    chat()
