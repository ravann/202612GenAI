import json
from pathlib import Path
from dotenv import find_dotenv, load_dotenv
from model_adapter import ModelConfig
from extractor import Extractor

CYAN, RESET = "\033[36m", "\033[0m"      # ANSI escape codes; work in most terminals

load_dotenv(find_dotenv())                             # as in 0_main.py: looks in this folder, then in each parent folder

HERE = Path(__file__).parent
CONFIG = ModelConfig.load(HERE / "model.toml")

def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():                           # a blank line is not a row
                rows.append(json.loads(line))
    return rows

TICKETS = {}
for t in load_jsonl(HERE / "tickets.jsonl"):
    TICKETS[t["id"]] = t["text"]

CASES = load_jsonl(HERE / "cases.jsonl")
for c in CASES:
    if "text" not in c:                                # t1-t8 take their text from tickets.jsonl: one source per ticket
        c["text"] = TICKETS[c["id"]]

v1 = Extractor(CONFIG, prompt="incident-v1", delimit=False, verbose=False)    # the Session 2 release before the defense
v2 = Extractor(CONFIG, prompt="incident-v2", verbose=False)                   # verbose=False: no footer per call

def show(extractor, tid):
    r = extractor.extract(TICKETS[tid])
    priority = None
    if r["data"]:                                      # data is None when the extraction failed
        priority = r["data"]["priority"]
    print(f"{CYAN}{r['prompt']} | {tid} | ok={r['ok']} | review reasons={len(r['reasons'])}{RESET}")
    print(f"    priority={priority}")

if __name__ == "__main__":
    for tid in ["t3", "t4", "t7"]:
        for extractor in [v1, v2]:
            show(extractor, tid)
