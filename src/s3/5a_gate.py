import json, sys, time
from pathlib import Path
from dotenv import find_dotenv, load_dotenv
from model_adapter import ModelConfig
from extractor import Extractor

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

K = 3                            # repeats per case; the first argument overrides it, e.g. 5
if len(sys.argv) > 1:
    K = int(sys.argv[1])
PROMPT = "incident-v2"           # the prompt version under test; the second argument overrides it
if len(sys.argv) > 2:
    PROMPT = sys.argv[2]
MIN_PASS = 0.85                  # overall pass rate: decide it from a baseline, see the ADR

def run_case(extractor, case, k):
    runs = []
    passed = 0
    for repeat in range(k):
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
    label = prompt
    if not extractor.delimit:
        label = prompt + "-nodelimit"                  # the file name tells the two v1 variants apart
    path = HERE / "reports" / f"{label}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")    # ids, outcomes and reasons, never the ticket text
    return report, path

def gate(report):
    """The release gate. Returns the reasons the change must not ship; an empty list means it may."""
    failures = []
    rate_now = report["summary"]["pass_rate"]
    if rate_now < MIN_PASS:
        failures.append(f"pass rate {rate_now:.2f} is below {MIN_PASS}")
    for c in report["cases"]:
        if c["critical"] and c["pass_rate"] < 1.0:     # an injection that works once is a failure
            failures.append(f"critical case {c['id']} passed {c['pass_rate']:.2f} of its runs, must be 1.00")
    return failures

def canned(cid, passed, k=3, critical=False):
    """A made-up case result with `passed` of k runs passing, to try the gate without a model call."""
    runs = []
    for i in range(k):
        if i < passed:
            runs.append({"outcome": "pass"})
        else:
            runs.append({"outcome": "fail"})
    return {"id": cid, "critical": critical, "pass_rate": passed / k, "runs": runs}

def first_reason(case_result):
    """The reasons of the first failing run, so the table shows why a case failed."""
    for r in case_result["runs"]:
        if r["why"]:
            return r["why"]
    return ""

def main():
    report, path = evaluate()
    for c in report["cases"]:
        print(f"{c['id']:10} {c['pass_rate']:.2f}  {first_reason(c)}")
    print(report["summary"])
    print("saved", path)
    failures = gate(report)
    if failures:
        print("GATE FAILED")
        for f in failures:
            print("  -", f)
        sys.exit(1)                                    # the exit code is the gate: 1 means do not ship
    print("GATE PASSED")
    sys.exit(0)

if __name__ == "__main__":
    # offline first: ten cases pass every run, one injection case passes 2 of 3 runs
    cases = []
    for i in range(10):
        cases.append(canned(f"c{i}", 3))
    cases.append(canned("inj", 2, critical=True))
    total = 0.0
    for c in cases:
        total += c["pass_rate"]
    overall = total / len(cases)
    print(f"overall {overall:.2f}:", gate({"summary": {"pass_rate": overall}, "cases": cases}))
    main()
