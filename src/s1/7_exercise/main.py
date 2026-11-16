import os, sys, time
from pathlib import Path
from dotenv import load_dotenv
from model_adapter import ModelAdapter, ModelConfig

# The .env file is in the code folder, two levels up from this script (code/s1/7_exercise/main.py)
load_dotenv(Path(__file__).parent.parent.parent / ".env")

CYAN, RESET = "\033[36m", "\033[0m"      # ANSI escape codes; work in most terminals

def show(chunk):
    print(f"{CYAN}{chunk}{RESET}", end="", flush=True)   # reset per chunk so an interrupt can't leave the terminal tinted

def chat(model):
    history = []
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if q in ["exit", "quit", "q"]:
            break
        if q == "":
            continue
        history.append({"role": "user", "content": q})
        started = time.perf_counter()
        result = model.safe_stream(history, on_text=show)
        if result is None:
            history.pop()                                     # keep user/assistant turns alternating
            continue
        resp, ttft = result
        seconds = time.perf_counter() - started
        text = model.text_of(resp)
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
            model.report(resp, seconds, ttft)
        except (KeyError, OSError) as e:                      # a logging or pricing problem must not kill the chat
            print(f"[usage logging failed: {e!r}]")
        history.append({"role": "assistant", "content": text})   # state is the application's job


if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):                    # otherwise the first request fails with a TypeError
        sys.exit("ANTHROPIC_API_KEY is not set (expected in code/.env)")
    config_path = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("model.toml")
    chat(ModelAdapter(ModelConfig.load(config_path)))
