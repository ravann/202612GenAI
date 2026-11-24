import json, math, sys

CYAN, RESET = "\033[36m", "\033[0m"      # ANSI escape codes; work in most terminals

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def shown(rate):
    if rate is None:
        return " n/a"                                  # every run of the case failed at the API: nothing was graded
    return f"{rate:.2f}"

if len(sys.argv) != 3:
    sys.exit("usage: python code/s3/6b_compare_reports.py <older report> <newer report>")
a = load(sys.argv[1])                                  # two saved reports: no model call, no cost
b = load(sys.argv[2])
if a.get("stopped") or b.get("stopped"):               # reports from steps 3 and 4 have no "stopped" key
    sys.exit("refusing to compare a run that stopped early")
if a["k"] != b["k"] or a["summary"]["runs"] != b["summary"]["runs"]:
    sys.exit("refusing to compare reports made with a different k or a different set of cases")

rates_b = {}
for c in b["cases"]:
    rates_b[c["id"]] = c["pass_rate"]
for c in a["cases"]:
    before = c["pass_rate"]
    after = rates_b.get(c["id"])
    marker = ""
    if before != after:
        marker = "   <- changed"
    print(f"{CYAN}{c['id']:10} {shown(before)} -> {shown(after)}{marker}{RESET}")

pa = a["summary"]["pass_rate"]
pb = b["summary"]["pass_rate"]
n = a["summary"]["runs"]
p = (pa + pb) / 2
noise = 2 * math.sqrt(2 * p * (1 - p) / n)            # about a 95% band for a difference of two pass rates, a lower bound
floor = 3 / n                                          # "rule of three": no failure in n runs still allows a failure rate up to about 3/n
if noise < floor:                                      # so two perfect runs do not print a band of zero
    noise = floor
if abs(pb - pa) <= noise:
    meaning = "inside the noise, not evidence"
else:
    meaning = "larger than the noise"
print(f"{CYAN}overall {pa:.2f} -> {pb:.2f}: difference {pb - pa:+.2f}, noise about +-{noise:.2f}: {meaning}{RESET}")
print(f"{CYAN}cost ${a['summary']['cost_usd']:.3f} -> ${b['summary']['cost_usd']:.3f} | "
      f"repairs {a['summary']['repair_rate']:.2f} -> {b['summary']['repair_rate']:.2f}{RESET}")
