import json, re, sys
from pathlib import Path

CYAN, RESET = "\033[36m", "\033[0m"      # ANSI escape codes; work in most terminals

HERE = Path(__file__).parent

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

hits = []
prompt_files = sorted((HERE / "prompts").glob("*.md")) + sorted((HERE / "mutants").glob("*.md"))
for prompt_file in prompt_files:
    body = prompt_file.read_text(encoding="utf-8")
    for c in CASES:
        leaked = c["text"] in body                     # the whole case text, pasted into a prompt
        for ticket_id in re.findall(r"INC-\d+", c["text"]):
            if ticket_id in body:                      # a case's ticket ID in a prompt is already a leak
                leaked = True
        if leaked:
            hits.append(f"{prompt_file.name} contains test case {c['id']}")

if hits:
    print(f"{CYAN}LEAK:{RESET}")
    for h in hits:
        print(f"{CYAN}  {h}{RESET}")
    sys.exit(1)
print(f"{CYAN}no test case appears in any prompt file{RESET}")
