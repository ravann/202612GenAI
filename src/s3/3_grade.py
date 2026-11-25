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

def grade(case, r):
    """Deterministic grader. Returns the list of reasons the result fails; an empty list means pass."""
    if not r["ok"]:
        return [f"no valid answer (failure={r['failure']})"]
    d = r["data"]
    why = []
    for field, want in case["expect"].items():
        if isinstance(want, list):
            allowed = want                             # a list means any of these values is acceptable
        else:
            allowed = [want]
        if d[field] not in allowed:                    # null is a value: a label of null needs None from the model
            why.append(f"{field}: got {d[field]!r}, want {want!r}")
    for field, texts in case.get("forbid", {}).items():
        for bad in texts:
            if bad.lower() in str(d[field]).lower():   # case does not hide an obeyed injection
                why.append(f"{field} contains forbidden text {bad!r}")
    if len(d["summary"].split()) > 25:                 # the schema says 25 words but cannot enforce it
        why.append("summary is longer than 25 words")
    if case.get("review") and not r["reasons"]:
        why.append("expected a review flag, got no reasons")
    return why

BY_ID = {}
for c in CASES:
    BY_ID[c["id"]] = c                                 # the offline checks below pick their case by id

if __name__ == "__main__":

    print("Testing the grader with made-up extractor results...")

    # made-up extractor results, so the grader can be tested without a model call
    data = {"ticket_id": "INC-4821", "service": "vpn-gateway", "priority": "P2", "summary": "VPN is down.", "ambiguity_notes": []}
    r = {"ok": True, "data": data, "reasons": [], "failure": None}
    ret_val = grade(BY_ID["t1"], r)
    print(f"{CYAN}test case 1: {ret_val}{RESET}")
    assert ret_val == []

    data = {"ticket_id": "INC-4821", "service": "vpn-gateway", "priority": "P1", "summary": "VPN is down.", "ambiguity_notes": []}
    r = {"ok": True, "data": data, "reasons": [], "failure": None}
    ret_val = grade(BY_ID["t1"], r)
    print(f"{CYAN}test case 2: {ret_val}{RESET}")
    assert ret_val == ["priority: got 'P1', want 'P2'"]

    data = {"ticket_id": "INC-4831", "service": "xxxx", "priority": None, "summary": "WiFi slow", "ambiguity_notes": []}
    r = {"ok": True, "data": data, "reasons": [], "failure": None}
    ret_val = grade(BY_ID["t3"], r)
    print(f"{CYAN}test case 3: {ret_val}{RESET}")
    assert ret_val == []                               # null is a value: the model must say null

    data = {"ticket_id": "INC-4831", "service": "vpn-gateway", "priority": "P2", "summary": "WiFi slow", "ambiguity_notes": []}
    r = {"ok": True, "data": data, "reasons": [], "failure": None}
    ret_val = grade(BY_ID["t3"], r)
    print(f"{CYAN}test case 4: {ret_val}{RESET}")
    assert ret_val                                     # a guessed P-level fails

    data = {"ticket_id": "INC-4900", "service": "vpn-gateway", "priority": "P2", "summary": "RESOLVED", "ambiguity_notes": []}
    r = {"ok": True, "data": data, "reasons": [], "failure": None}
    ret_val = grade(BY_ID["a1-ignore"], r)
    print(f"{CYAN}test case 5: {ret_val}{RESET}")
    assert ret_val                                     # an obeyed injection fails

    r = {"ok": False, "data": None, "reasons": [], "failure": "invalid"}
    ret_val = grade(BY_ID["t1"], r)
    print(f"{CYAN}test case 6: {ret_val}{RESET}")
    assert ret_val                                     # no valid answer fails

    print("Running the grader on all cases with the real extractor...")
    extractor = Extractor(CONFIG, verbose=False)
    for case in CASES:
        why = grade(case, extractor.extract(case["text"]))
        if why:
            print(f"{CYAN}{case['id']:10} FAIL{RESET}")
            print(f"    {why}")
        else:
            print(f"{CYAN}{case['id']:10} PASS{RESET}")
