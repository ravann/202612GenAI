import json, os, sys
from pathlib import Path
from dotenv import find_dotenv, load_dotenv
from model_adapter import ModelConfig
from extractor import Extractor
from evalkit import rate, run_all, save_report, summarise, verdict

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

def evaluate(prompt=PROMPT, k=K, max_cost=MAX_COST, config=CONFIG, **options):
    """Run the suite against one Extractor. options go to Extractor (prompts_dir, delimit). Saves and returns the report."""
    extractor = Extractor(config, prompt=prompt, verbose=False, **options)     # verbose=False: this report is the log

    def run(case):                                     # the kit calls this once per run: the only code that knows the extractor
        return extractor.extract(case["text"])

    results, stopped = run_all(run, grade, CASES, k, max_cost, ABORT_AFTER)
    for c in results:
        c["pass_rate"] = rate(c)
    report = {"prompt": prompt, "model": config.model, "delimit": extractor.delimit, "k": k, "stopped": stopped,
              "summary": summarise(results), "cases": results}
    label = prompt
    if not extractor.delimit:
        label = prompt + "-nodelimit"                  # the file name tells the two v1 variants apart
    return report, save_report(report, HERE / "reports", label)

def first_reason(case_result):
    """The reasons of the first failing run, so the table shows why a case failed."""
    for r in case_result["runs"]:
        if r["why"]:
            return r["why"]
    return ""

def main():
    if not os.getenv("ANTHROPIC_API_KEY"):             # no key: the run cannot ask the question, so there is no verdict
        print("NO VERDICT: ANTHROPIC_API_KEY is not set (expected in code/.env)")
        sys.exit(2)
    if not CASES:                                      # an empty suite cannot pass or fail anything
        print("NO VERDICT: no cases in cases.jsonl")
        sys.exit(2)
    report, path = evaluate()
    for c in report["cases"]:
        if c["pass_rate"] is None:
            shown = "n/a"                              # every run of this case failed at the API: nothing was graded
        else:
            shown = f"{c['pass_rate']:.2f}"
        print(f"{c['id']:10} {shown}  {first_reason(c)}")
    print(report["summary"])
    print("saved", path)
    sys.exit(verdict(report, MIN_PASS, MAX_API_SHARE))     # the exit code is the gate: 0 ship, 1 do not ship, 2 no verdict

if __name__ == "__main__":
    main()
