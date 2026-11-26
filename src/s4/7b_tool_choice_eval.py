import json, os, sys, time
from dataclasses import replace
from pathlib import Path
import anthropic
from model_adapter import ModelAdapter
from evalkit import rate, run_all, save_report, summarise, verdict
from servicedesk_tools import CONFIG, SYSTEM, TOOLS, cost_of

# The tool-choice eval: does the model pick the right tool (or no tool), with the right arguments, for each request?
# It grades the model's FIRST decision only: one model call per run, and no tool is executed, so ServiceDesk is not
# needed. A write that follows a look-up is invisible to it; grading whole runs is Session 7.
# The runner, the rates, the gate and the report come from the Session 3 kit, evalkit.py.

HERE = Path(__file__).parent

def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():                           # a blank line is not a row
                rows.append(json.loads(line))
    return rows

CASES = load_jsonl(HERE / "tool_cases.jsonl")
TAG = {}
for c in CASES:
    TAG[c["id"]] = c["tag"]

READ_TOOLS = ["search_incidents", "get_incident", "find_asset", "get_asset_dependencies"]   # look-ups change nothing

K = 2                            # repeats per case: the first argument, e.g. python 7b_tool_choice_eval.py 3
if len(sys.argv) > 1:
    K = int(sys.argv[1])
MODEL_ID = CONFIG.model          # the model from model.toml, or the second argument: ... 7b_tool_choice_eval.py 2 claude-haiku-5-5
if len(sys.argv) > 2:
    MODEL_ID = sys.argv[2]
DRAFTS = []                      # Segment 4: the third argument "drafts" adds two of the generator's drafts
if len(sys.argv) > 3 and sys.argv[3] == "drafts":
    DRAFTS = ["approve_change", "update_incident"]     # hidden and wrapped in 4b_curate.py: what if we had not?
MAX_COST = 0.50                  # USD per eval run: the run stops when the spend passes this
ABORT_AFTER = 3                  # this many api failures in a row mean the setup is broken, not the tools
MAX_API_SHARE = 0.10             # more api failures than this and the pass rate is not trustworthy
MIN_PASS = 0.90                  # overall; the cases marked critical must pass every run

MODEL = ModelAdapter(replace(CONFIG, model=MODEL_ID, system=SYSTEM))

EVAL_TOOLS = []                  # what the model is offered: the six curated tools, plus the drafts if asked for
for tool in TOOLS:
    EVAL_TOOLS.append(tool)
for d in json.loads((HERE / "generated_tools.json").read_text(encoding="utf-8")):
    if d["name"] in DRAFTS:                            # only what the model reads: no x-http, no x-risk
        EVAL_TOOLS.append({"name": d["name"], "description": d["description"], "input_schema": d["input_schema"]})

def run(case):
    """One run: one model call with the tools. Returns what the kit needs, plus the tool calls the model asked for."""
    started = time.perf_counter()
    try:
        resp = MODEL.ask([{"role": "user", "content": case["prompt"]}], tools=EVAL_TOOLS, tool_choice={"type": "auto"})
    except anthropic.APIError as e:                    # after the SDK's own retries: infrastructure, not tool choice
        return {"failure": "api", "errors": [f"{type(e).__name__}: {e}"], "cost_usd": 0.0,
                "seconds": time.perf_counter() - started, "calls": []}
    calls = []
    for block in resp.content:
        if block.type == "tool_use":
            calls.append({"name": block.name, "input": block.input})
    failure = None
    if resp.stop_reason in ("max_tokens", "refusal"):
        failure = "incomplete"                         # graded as a failure, as in Session 3
    return {"failure": failure, "errors": [], "cost_usd": cost_of(MODEL, resp),
            "seconds": time.perf_counter() - started, "calls": calls}

def grade(case, r):
    """Returns the reasons this run fails; an empty list means it passed."""
    if r["failure"] is not None:
        return [f"no usable answer (failure={r['failure']})"]
    called = []
    for call in r["calls"]:
        called.append(call["name"])
    if case["tag"] == "no-tool":
        if called:
            return [f"called {', '.join(called)}, want no tool"]
        return []
    if case["tag"] == "refuse":                        # a look-up first is fine; any other tool is not (fail closed)
        why = []
        for name in called:
            if name not in READ_TOOLS:
                why.append(f"called {name}, want a refusal")
        return why
    want = case["expect_tool"]                         # select and arguments
    if want not in called:
        looked_up = len(called) > 0                    # only look-ups this case allows, before the expected write
        for name in called:
            if name not in case.get("may_look_up", []):
                looked_up = False
        if looked_up:
            return []
        if called:
            return [f"called {', '.join(called)}, want {want}"]
        return [f"called no tool, want {want}"]
    why = []
    for call in r["calls"]:                            # parallel calls: one call of the expected tool must match
        if call["name"] != want:
            continue
        why = []
        for key, value in case.get("expect_args", {}).items():
            got = call["input"].get(key)               # a left-out argument is None, which is JSON null
            if got != value:
                why.append(f"{key}: got {json.dumps(got)}, want {json.dumps(value)}")
        if not why:
            return []
    return why

def tag_rates(results):
    """Pass rate per tag, over the graded runs (api failures are not graded)."""
    counts = {}
    for c in results:
        tag = TAG[c["id"]]
        if tag not in counts:
            counts[tag] = {"passed": 0, "graded": 0}
        for r in c["runs"]:
            if r["outcome"] != "api":
                counts[tag]["graded"] += 1
            if r["outcome"] == "pass":
                counts[tag]["passed"] += 1
    rates = {}
    for tag, n in counts.items():
        rates[tag] = f"{n['passed']}/{n['graded']}"
    return rates

def first_reason(case_result):
    """The reasons of the first failing run, so the table shows why a case failed."""
    for r in case_result["runs"]:
        if r["why"]:
            return r["why"]
    return ""

def main():
    if not os.getenv("ANTHROPIC_API_KEY"):             # no key: the run cannot ask the question, so there is no verdict
        print("NO VERDICT: ANTHROPIC_API_KEY is not set (expected in src/.env)")
        sys.exit(2)
    if DRAFTS:
        print("the six curated tools plus the generator's drafts:", ", ".join(DRAFTS))
    results, stopped = run_all(run, grade, CASES, K, MAX_COST, ABORT_AFTER)
    for c in results:
        c["pass_rate"] = rate(c)
    report = {"eval": "tool-choice", "model": MODEL.config.model, "k": K, "drafts": DRAFTS, "stopped": stopped,
              "summary": summarise(results), "tags": tag_rates(results), "cases": results}
    path = save_report(report, HERE / "reports", "tool-choice")
    for c in report["cases"]:
        if c["pass_rate"] is None:
            shown = "n/a"                              # every run of this case failed at the API: nothing was graded
        else:
            shown = f"{c['pass_rate']:.2f}"
        print(f"{c['id']:6} {TAG[c['id']]:9} {shown}  {first_reason(c)}")
    print("per tag (passed/graded runs):", report["tags"])
    print(report["summary"])
    print("saved", path)
    sys.exit(verdict(report, MIN_PASS, MAX_API_SHARE))     # the exit code is the gate: 0 ship, 1 do not ship, 2 no verdict

if __name__ == "__main__":
    main()
