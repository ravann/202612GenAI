import json, os, sys
from pathlib import Path
from dotenv import find_dotenv, load_dotenv
from model_adapter import ModelConfig
from extractor import Extractor

CYAN, RESET = "\033[36m", "\033[0m"      # ANSI escape codes; work in most terminals

# The .env file is in the code folder: find_dotenv() looks in this folder and then in each parent folder
load_dotenv(find_dotenv())

HERE = Path(__file__).parent
PROMPT = "incident-v2"                       # change to "incident-v1" to roll back: the file name is the version

def main():
    tickets = [json.loads(line) for line in open(HERE / "tickets.jsonl", encoding="utf-8") if line.strip()]
    ids = ["t1", "t2"]
    if ids:
        tickets = [t for t in tickets if t["id"] in ids]
    extractor = Extractor(ModelConfig.load(HERE / "model.toml"), prompt=PROMPT)
    total, unknown = 0.0, 0
    for t in tickets:
        r = extractor.extract(t["text"])
        if r["cost_usd"] is None:            # no price for the model in model.toml: the call was billed, the cost is unknown
            unknown += 1
            cost = "cost unknown"
        else:
            total += r["cost_usd"]
            cost = f"${r['cost_usd']:.4f}"
        status = "ok" if r["ok"] else f"FAILED ({r['failure']})"
        print(f"{CYAN}{t['id']} | {status} | attempts={r['attempts']} | prompt={r['prompt']} | needs_review={bool(r['reasons'])} | {cost} | {r['seconds']:.1f}s{RESET}")
        print(f"    data={r['data']}\n    reasons={r['reasons']}")
    print(f"{CYAN}total cost ${total:.4f}" + (f", plus {unknown} tickets of unknown cost" if unknown else "") + RESET)

if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):   # otherwise the first request fails with a TypeError
        sys.exit("ANTHROPIC_API_KEY is not set (expected in code/.env)")
    main()
