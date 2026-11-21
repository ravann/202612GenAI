import json, sys, time
from dataclasses import replace         # only for the model comparison in main()
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
MAX_COST = 0.50                  # USD per suite run: the run stops when the spend passes this
ABORT_AFTER = 3                  # this many api failures in a row mean the setup is broken, not the prompt
MAX_API_SHARE = 0.10             # more api failures than this and the pass rate is not trustworthy
MIN_PASS = 0.85                  # overall pass rate: decide it from a baseline, see the ADR

def run_all(extractor, cases, k, max_cost=MAX_COST):
    """Returns (results, stopped). stopped is None for a complete run, otherwise the reason it ended early."""
    results = []
    spent = 0.0
    streak = 0                                         # api failures in a row, across case boundaries
    for case in cases:
        case_result = {"id": case["id"], "critical": bool(case.get("critical")), "pass_rate": None, "runs": []}
        results.append(case_result)                    # added first, so a run that stops early still reports this case
        for repeat in range(k):
            r = extractor.extract(case["text"])
            if r["cost_usd"] is not None:              # None: model.toml has no price for the model
                spent += r["cost_usd"]
            if r["failure"] == "api":                  # infrastructure, not quality: never graded
                outcome = "api"
                why = [r["errors"][-1][:300]]
                streak += 1
            else:
                why = grade(case, r)                   # "invalid" and "incomplete" are graded: the answer was unusable
                streak = 0
                if why:
                    outcome = "fail"
                else:
                    outcome = "pass"
            case_result["runs"].append({"outcome": outcome, "why": why, "attempts": r["attempts"],
                                        "cost_usd": r["cost_usd"], "seconds": r["seconds"]})
            if streak >= ABORT_AFTER:
                return results, f"{streak} api failures in a row, last: {why[0]}"
            if r["cost_usd"] is None:                  # a guard cannot cap a spend it cannot see
                return results, "cost guard: cost unknown (model.toml has no price for this model), so the spend cannot be capped"
            if spent > max_cost:
                return results, f"cost guard: ${spent:.3f} passed the cap of ${max_cost:.2f}"
    return results, None

def rate(case_result):
    """Pass rate over the runs that were graded, or None if every run failed at the API."""
    graded = 0
    passed = 0
    for r in case_result["runs"]:
        if r["outcome"] != "api":
            graded += 1
        if r["outcome"] == "pass":
            passed += 1
    if graded == 0:
        return None
    return passed / graded

def summarise(results):
    """Totals over every run of every case. api runs are counted, but they were never graded, so not in the rates."""
    runs = 0
    api_failures = 0
    passed = 0
    repaired = 0
    cost = 0.0
    seconds = 0.0
    slowest = 0.0
    for c in results:
        for r in c["runs"]:
            runs += 1
            if r["outcome"] == "api":
                api_failures += 1
            if r["outcome"] == "pass":
                passed += 1
            if r["outcome"] != "api" and r["attempts"] > 1:     # S2: a rising repair rate is a regression signal
                repaired += 1
            if r["cost_usd"] is not None:              # None: model.toml has no price for the model, the cost is unknown
                cost += r["cost_usd"]
            seconds += r["seconds"]
            slowest = max(slowest, r["seconds"])
    graded = runs - api_failures
    pass_rate = 0.0
    repair_rate = 0.0
    if graded > 0:                                     # nothing graded: the rates mean nothing, and verdict() says so
        pass_rate = passed / graded
        repair_rate = repaired / graded
    return {"runs": runs,
            "api_failures": api_failures,
            "pass_rate": round(pass_rate, 3),
            "repair_rate": round(repair_rate, 3),
            "cost_usd": round(cost, 4),
            "seconds_mean": round(seconds / runs, 2),
            "seconds_max": round(slowest, 2)}

def evaluate(prompt=PROMPT, k=K, max_cost=MAX_COST, config=CONFIG, **options):
    """Run the suite against one Extractor. options go to Extractor (prompts_dir, delimit). Saves and returns the report."""
    extractor = Extractor(config, prompt=prompt, verbose=False, **options)     # verbose=False: this report is the log
    results, stopped = run_all(extractor, CASES, k, max_cost)
    for c in results:
        c["pass_rate"] = rate(c)
    report = {"prompt": prompt, "model": config.model, "delimit": extractor.delimit, "k": k, "stopped": stopped,
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
        case_rate = c["pass_rate"]
        if case_rate is None:                          # never graded (every run failed at the API): no evidence it is safe
            case_rate = 0.0
        if c["critical"] and case_rate < 1.0:          # an injection that works once is a failure
            failures.append(f"critical case {c['id']} passed {case_rate:.2f} of its runs, must be 1.00")
    return failures

def verdict(report):
    """Exit code: 0 gate passed, 1 gate failed, 2 no verdict because the run itself is not trustworthy."""
    s = report["summary"]
    if report["stopped"]:
        print("NO VERDICT:", report["stopped"])
        return 2
    if s["api_failures"] / s["runs"] > MAX_API_SHARE:
        print(f"NO VERDICT: {s['api_failures']} of {s['runs']} runs failed at the API, not at the task")
        return 2
    failures = gate(report)
    if failures:
        print("GATE FAILED")
        for f in failures:
            print("  -", f)
        return 1
    print("GATE PASSED")
    return 0

def show(report, path):
    s = report["summary"]
    print(f"{path.name}: pass {s['pass_rate']:.2f} | repairs {s['repair_rate']:.2f} | ${s['cost_usd']:.3f} | stopped={report['stopped']}")

def main():
    old, old_path = evaluate("incident-v1", delimit=False)          # two Extractors, one suite: nothing is edited between runs
    show(old, old_path)
    new, new_path = evaluate("incident-v2")
    show(new, new_path)
    # a second model is a second config on the same prompt (instructor demo; the model needs a [prices] row):
    # cheap, cheap_path = evaluate("incident-v2", config=replace(CONFIG, model="claude-haiku-5-5"))
    # show(cheap, cheap_path)
    print("next: python code/s3/6b_compare_reports.py <older report> <newer report>")

if __name__ == "__main__":
    main()
