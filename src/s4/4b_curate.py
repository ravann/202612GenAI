import json, sys
from pathlib import Path
from servicedesk_tools import TOOLS

# ANSI escape codes, as in Session 3. CYAN: what this program prints. GREEN: what the model produced.
# Tool responses keep the terminal's default color (black would vanish on a dark theme).
CYAN, GREEN, RESET = "\033[36m", "\033[32m", "\033[0m"

# Generate, then curate: decide for every ServiceDesk operation whether the agent gets it as it is (expose),
# as a narrower task-level tool (wrap), or not at all (hide). No model call and no ServiceDesk call.

HERE = Path(__file__).parent

DECISIONS = {      # operationId: (decision, curated tool, reason)
    "list_incidents":         ("wrap",   "search_incidents",       "task-level search: at most 20 results, 8 fields"),
    "create_incident":        ("hide",   "",                       "not a Compass task; an agent could flood the queue"),
    "get_incident":           ("expose", "get_incident",           "fine as it is, with fewer fields"),
    "update_incident":        ("wrap",   "assign_incident",        "one safe action: the assignee, never the status"),
    "add_incident_comment":   ("hide",   "",                       "a write no task needs; people and agents read comments"),
    "list_assets":            ("wrap",   "find_asset",             "search by a word: at most 10 results, 6 fields"),
    "get_asset":              ("hide",   "",                       "find_asset returns the same fields: fewer, distinct tools"),
    "get_asset_dependencies": ("expose", "get_asset_dependencies", "fine as it is"),
    "list_changes":           ("hide",   "",                       "no Session 4 task needs it: fewer tools choose better"),
    "get_change":             ("hide",   "",                       "no Session 4 task needs it"),
    "create_change":          ("wrap",   "propose_change_request", "a proposal; the idempotency key is made in code"),
    "approve_change":         ("hide",   "",                       "privileged: a change manager approves, never the agent"),
    "list_runbooks":          ("hide",   "",                       "Session 5 adds search_runbooks, with access control"),
    "get_runbook":            ("hide",   "",                       "Session 5 (search_runbooks)"),
    "set_faults":             ("hide",   "",                       "test control"),
    "reset_data":             ("hide",   "",                       "test control"),
}

def size(tool):
    """How many characters the model reads for one tool: its name, description and input schema."""
    return len(json.dumps({"name": tool["name"], "description": tool["description"], "input_schema": tool["input_schema"]}))

if __name__ == "__main__":
    path = HERE / "generated_tools.json"               # the pre-generated drafts
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])                       # or a fresh run: python 4b_curate.py reports/generated_tools.json
    drafts = json.loads(path.read_text(encoding="utf-8"))
    drafts_by_name = {}
    for d in drafts:
        drafts_by_name[d["name"]] = d
    curated = {}
    for tool in TOOLS:
        curated[tool["name"]] = tool

    counts = {"expose": 0, "wrap": 0, "hide": 0}
    print(f"{CYAN}{'operation':23} {'HTTP':39} {'decision':8} {'curated tool':23} reason{RESET}")
    for d in drafts:
        if d["name"] not in DECISIONS:                 # a new operation in the API: someone must decide, not default
            print(f"{CYAN}{d['name']:23} {d['x-http']:39} NO DECISION YET{RESET}")
            continue
        decision, tool_name, reason = DECISIONS[d["name"]]
        counts[decision] += 1
        print(f"{CYAN}{d['name']:23} {d['x-http']:39} {decision:8} {tool_name:23} {reason}{RESET}")
    print(f"{CYAN}{len(drafts)} drafts: {counts['expose']} exposed, {counts['wrap']} wrapped, {counts['hide']} hidden. "
          f"Curated tools in servicedesk_tools.py: {len(TOOLS)}{RESET}")
    print(f"{CYAN}approve_change is a draft: {'approve_change' in drafts_by_name}. "
          f"It is a curated tool: {'approve_change' in curated}{RESET}")

    print()
    print(f"{CYAN}Before and after, for two operations (characters the model reads, and the properties it may fill in){RESET}")
    for draft_name, tool_name in [("list_incidents", "search_incidents"), ("create_change", "propose_change_request")]:
        draft = drafts_by_name[draft_name]
        tool = curated[tool_name]
        print(f"{CYAN}  draft   {draft_name:23} {size(draft):5}  {list(draft['input_schema']['properties'])}{RESET}")
        print(f"{CYAN}  curated {tool_name:23} {size(tool):5}  {list(tool['input_schema']['properties'])}{RESET}")
