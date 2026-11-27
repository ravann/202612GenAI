# The reusable part of the Session 3 eval: the runner, the rates, the gate, the exit code and the report file.
# It knows nothing about tickets or extractors: the caller passes run(case) and grade(case, result).
# Session 4's tool-choice eval uses the same functions with its own run and grade.
import json, time
from pathlib import Path

# ANSI escape codes, as in Session 3. CYAN: what this program prints. GREEN: what the model produced.
# Tool responses keep the terminal's default color (black would vanish on a dark theme).
CYAN, GREEN, RESET = "\033[36m", "\033[32m", "\033[0m"


def run_all(run, grade, cases, k, max_cost=0.50, abort_after=3):
    """Run every case k times. Returns (results, stopped): stopped is None for a complete run, otherwise the reason.
    run(case) returns a dict with at least failure (None or "api"), errors (a list of strings), cost_usd (a number,
    or None if unknown) and seconds; attempts is optional and counts as 1. grade(case, result) returns a list of reasons."""
    results = []
    spent = 0.0
    streak = 0                                         # api failures in a row, across case boundaries
    for case in cases:
        case_result = {"id": case["id"], "critical": bool(case.get("critical")), "pass_rate": None, "runs": []}
        results.append(case_result)                    # added first, so a run that stops early still reports this case
        for repeat in range(k):
            r = run(case)
            if r["cost_usd"] is not None:
                spent += r["cost_usd"]
            if r["failure"] == "api":                  # infrastructure, not quality: never graded
                outcome = "api"
                last_error = "no error text"           # a run() may report an api failure with an empty errors list
                if r["errors"]:
                    last_error = r["errors"][-1][:300]
                why = [last_error]
                streak += 1
            else:
                why = grade(case, r)                   # any other failure is graded: the answer was unusable
                streak = 0
                if why:
                    outcome = "fail"
                else:
                    outcome = "pass"
            case_result["runs"].append({"outcome": outcome, "why": why, "attempts": r.get("attempts", 1),
                                        "cost_usd": r["cost_usd"], "seconds": r["seconds"]})
            if streak >= abort_after:
                return results, f"{streak} api failures in a row, last: {why[0]}"
            if r["cost_usd"] is None:                  # a guard cannot cap a spend it cannot see
                return results, "cost guard: a run reported no cost, so the spend cannot be capped"
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
            if r["outcome"] != "api" and r["attempts"] > 1:     # a rising repair rate is a regression signal
                repaired += 1
            if r["cost_usd"] is not None:              # None: the cost is unknown
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


def gate(report, min_pass):
    """The release gate. Returns the reasons the change must not ship; an empty list means it may."""
    failures = []
    rate_now = report["summary"]["pass_rate"]
    if rate_now < min_pass:
        failures.append(f"pass rate {rate_now:.2f} is below {min_pass}")
    for c in report["cases"]:
        case_rate = c["pass_rate"]
        if case_rate is None:                          # never graded (every run failed at the API): no evidence it is safe
            case_rate = 0.0
        if c["critical"] and case_rate < 1.0:          # a critical case must pass every run
            failures.append(f"critical case {c['id']} passed {case_rate:.2f} of its runs, must be 1.00")
    return failures


def verdict(report, min_pass=0.85, max_api_share=0.10):
    """Prints the verdict and returns the exit code: 0 gate passed, 1 gate failed, 2 no verdict."""
    s = report["summary"]
    if report["stopped"]:
        print(f"{CYAN}NO VERDICT: {report['stopped']}{RESET}")
        return 2
    if s["api_failures"] / s["runs"] > max_api_share:
        print(f"{CYAN}NO VERDICT: {s['api_failures']} of {s['runs']} runs failed at the API, not at the task{RESET}")
        return 2
    failures = gate(report, min_pass)
    if failures:
        print(f"{CYAN}GATE FAILED{RESET}")
        for f in failures:
            print(f"{CYAN}  - {f}{RESET}")
        return 1
    print(f"{CYAN}GATE PASSED{RESET}")
    return 0


def save_report(report, folder, label):
    """Writes the report to folder/<label>-<date>-<time>.json and returns the path."""
    path = Path(folder) / f"{label}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")    # ids, outcomes and reasons, never the input text
    return path
