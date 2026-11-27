from pathlib import Path
import json, math, sys


CYAN, YELLOW, RESET = "\033[36m", "\033[33m", "\033[0m"     # ANSI escape codes; work in most terminals

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def shown(rate):
    if rate is None:
        return " n/a"                                  # every run of the case failed at the API: nothing was graded
    return f"{rate:.2f}"

def label(report):
    """A short column name, e.g. 'v1 sonnet nodelim'. Old reports (steps 3 and 4) have no model or delimit key."""
    name = report["prompt"].replace("incident-", "")
    model = report.get("model")
    if model:
        name += " " + model.replace("claude-", "").split("-")[0]
    if report.get("delimit") is False:
        name += " nodelim"
    return name

def noise_band(pa, pb, n):
    p = (pa + pb) / 2
    noise = 2 * math.sqrt(2 * p * (1 - p) / n)        # about a 95% band for a difference of two pass rates, a lower bound
    floor = 3 / n                                      # "rule of three": no failure in n runs still allows a failure rate up to about 3/n
    return max(noise, floor)                           # so two perfect runs do not print a band of zero

HERE = Path(__file__).parent
FILES = [                                              # saved reports, oldest first: no model call, no cost
    "incident-v1-claude-sonnet-5-5-nodelimit-20261127-181401.json",
    "incident-v1-claude-sonnet-5-5-20261127-181640.json",
    "incident-v1-claude-haiku-5-5-20261127-181826.json",
    "incident-v2-claude-sonnet-5-5-20261127-182041.json",
    "incident-v2-claude-haiku-5-5-20261127-182205.json",
]

reports = []                                           # (column name, report), only the ones fit to compare
for name in FILES:
    path = HERE / "reports" / name
    r = load(path)
    if r.get("stopped"):                               # an early stop leaves cases unrun: drop this run, keep comparing the rest
        print(f"{YELLOW}skipped {path.name}: stopped early ({r['stopped']}){RESET}")
        continue
    if reports:
        base = reports[0][1]
        if r["k"] != base["k"] or r["summary"]["runs"] != base["summary"]["runs"]:
            print(f"{YELLOW}skipped {path.name}: different k or set of cases than {reports[0][0]}{RESET}")
            continue
    reports.append((label(r), r))
    print(f"{CYAN}using   {path.name}{RESET}")

if len(reports) < 2:
    sys.exit(f"need at least two complete reports to compare, found {len(reports)}")

W = max(len(name) for name, _ in reports) + 2          # column width
print()
print(f"{CYAN}{'case':10}" + "".join(f"{name:>{W}}" for name, _ in reports) + RESET)

rates = []                                             # one {case id: pass rate} per report
for _, r in reports:
    rates.append({c["id"]: c["pass_rate"] for c in r["cases"]})
for c in reports[0][1]["cases"]:                       # the oldest report sets the row order
    row = [rates[i].get(c["id"]) for i in range(len(reports))]
    marker = ""
    if len(set(row)) > 1:
        marker = "   <- differs"
    print(f"{CYAN}{c['id']:10}" + "".join(f"{shown(x):>{W}}" for x in row) + f"{marker}{RESET}")

def summary_row(title, key, fmt):
    print(f"{CYAN}{title:10}" + "".join(f"{format(r['summary'][key], fmt):>{W}}" for _, r in reports) + RESET)

print()
summary_row("pass", "pass_rate", ".2f")
summary_row("repairs", "repair_rate", ".2f")
summary_row("cost $", "cost_usd", ".3f")
summary_row("sec mean", "seconds_mean", ".2f")

base_name, base = reports[0]                           # every other run is compared with the oldest one
pa = base["summary"]["pass_rate"]
n = base["summary"]["runs"]
print()
print(f"{CYAN}against {base_name} ({pa:.2f}):{RESET}")
for name, r in reports[1:]:
    pb = r["summary"]["pass_rate"]
    noise = noise_band(pa, pb, n)
    if abs(pb - pa) <= noise:
        meaning = "inside the noise, not evidence"
    else:
        meaning = "larger than the noise"
    print(f"{CYAN}  {name:{W}} {pb:.2f}: difference {pb - pa:+.2f}, noise about +-{noise:.2f}: {meaning}{RESET}")
