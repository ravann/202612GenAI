import json, sys, time
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

K = 3                            # repeats per case
PROMPT = "incident-v2"           # the prompt version under test

def run_case(extractor, case, k):
    runs = []
    passed = 0
    for repeat in range(k):
        print(f"Running case: {case['id']:10} iteration: {repeat+1}/{k}")
        r = extractor.extract(case["text"])
        why = grade(case, r)
        if why:
            outcome = "fail"
        else:
            outcome = "pass"
            passed += 1
        runs.append({"outcome": outcome, "why": why, "attempts": r["attempts"],
                     "cost_usd": r["cost_usd"], "seconds": r["seconds"]})
    return {"id": case["id"], "critical": bool(case.get("critical")), "pass_rate": passed / k, "runs": runs}

def summarise(results):
    """Totals over every run of every case."""
    runs = 0
    passed = 0
    repaired = 0
    cost = 0.0
    seconds = 0.0
    slowest = 0.0
    for c in results:
        for r in c["runs"]:
            runs += 1
            if r["outcome"] == "pass":
                passed += 1
            if r["attempts"] > 1:                      # S2: a rising repair rate is a regression signal
                repaired += 1
            if r["cost_usd"] is not None:              # None: model.toml has no price for the model, the cost is unknown
                cost += r["cost_usd"]
            seconds += r["seconds"]
            slowest = max(slowest, r["seconds"])
    return {"runs": runs,
            "pass_rate": round(passed / runs, 3),
            "repair_rate": round(repaired / runs, 3),
            "cost_usd": round(cost, 4),
            "seconds_mean": round(seconds / runs, 2),
            "seconds_max": round(slowest, 2)}

def evaluate(prompt=PROMPT, k=K, config=CONFIG, **options):
    """Run the suite against one Extractor. options go to Extractor (prompts_dir, delimit). Saves and returns the report."""
    extractor = Extractor(config, prompt=prompt, verbose=False, **options)     # verbose=False: this report is the log
    results = []
    for case in CASES:
        results.append(run_case(extractor, case, k))
    report = {"prompt": prompt, "model": config.model, "delimit": extractor.delimit, "k": k,
              "summary": summarise(results), "cases": results}
    label = f"{prompt}-{config.model}"
    if not extractor.delimit:
        label += "-nodelimit"                          # the file name tells the two v1 variants apart
    path = HERE / "reports" / f"{label}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")    # ids, outcomes and reasons, never the ticket text
    return report, path

def first_reason(case_result):
    """The reasons of the first failing run, so the table shows why a case failed."""
    for r in case_result["runs"]:
        if r["why"]:
            return r["why"]
    return ""

def main():
    report, path = evaluate()
    for c in report["cases"]:
        print(f"{CYAN}{c['id']:10} {c['pass_rate']:.2f}{RESET}")
        if first_reason(c):
            print(f"    {first_reason(c)}")
    print(f"{CYAN}{report['summary']}{RESET}")
    print(f"{CYAN}saved {path}{RESET}")

if __name__ == "__main__":
    main()
