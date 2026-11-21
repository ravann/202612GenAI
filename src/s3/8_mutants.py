import os, sys
from run_evals import HERE, evaluate, gate

FLIP = 0.6                     # a case flipped when its pass rate fell by more than half its runs, e.g. 3/3 to 1/3 or 0/3

MUTANTS = [                                                    # each one is a way to break incident-v2 on purpose
    ("priority on every ticket", {"prompt": "mutant-no-null", "prompts_dir": HERE / "mutants"}),
    ("tags but no rule", {"prompt": "incident-v1"}),           # v1 has no "data, not instructions" rule; delimit stays on
    ("rule but no tags", {"prompt": "incident-v2", "delimit": False}),
]

def flipped_cases(base, report):
    was = {}
    for c in base["cases"]:
        was[c["id"]] = c["pass_rate"]
    flipped = []
    for c in report["cases"]:
        now = c["pass_rate"]
        if now is None:                                # never graded counts as never passed
            now = 0.0
        if was[c["id"]] is not None and now <= was[c["id"]] - FLIP:
            flipped.append(c["id"])
    return flipped

if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):             # no key: the run cannot ask the question, so there is no verdict
        print("NO VERDICT: ANTHROPIC_API_KEY is not set (expected in code/.env)")
        sys.exit(2)
    base, base_path = evaluate("incident-v2")
    if base["stopped"]:
        sys.exit(f"the baseline stopped early, so there is nothing to compare with: {base['stopped']}")
    print(f"baseline pass {base['summary']['pass_rate']:.2f} | gate failures {len(gate(base))} | {base_path.name}")
    if gate(base):
        print("  the baseline fails its own gate: a mutant 'caught' by the gate alone proves nothing")
    for name, options in MUTANTS:
        report, path = evaluate(**options)             # each key of the dict becomes a keyword argument, e.g. delimit=False
        if report["stopped"]:
            print(f"{name:24} NO VERDICT: {report['stopped']}")
            if "api failures" in report["stopped"]:    # the API itself is failing: the next mutants would fail the same way
                break
        else:
            failures = gate(report)
            flipped = flipped_cases(base, report)
            if failures or flipped:
                result = "CAUGHT"
            else:
                result = "MISSED"
            print(f"{name:24} pass {report['summary']['pass_rate']:.2f} | gate failures {len(failures)} | flipped {flipped} | {result}")
            for f in failures:
                print("  -", f)
