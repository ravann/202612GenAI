import sys
from dataclasses import replace
from model_adapter import ModelAdapter
from servicedesk_tools import CONFIG, SYSTEM, TOOLS, ask_person, dispatch, money, run_with_tools

# Lab: try requests by hand against the finished tool layer (servicedesk_tools.py: six tools, the dispatcher with
# validation, scopes and confirmation). ServiceDesk must be running. Writes ask you to confirm at the terminal.

PROMPTS = ["What is open for the crm service?",                            # a clear request: one tool
           "What is a CMDB, in one sentence?",                             # needs no tool
           "Approve change 42.",                                           # must be refused: there is no approve tool
           "Which assets does INC-0013 involve, and what depends on them?", # several steps
           "Assign INC-0031 to dave."]                                     # a write: you confirm it, or not

if __name__ == "__main__":
    model = ModelAdapter(replace(CONFIG, system=SYSTEM))
    prompts = PROMPTS
    if len(sys.argv) > 1:
        prompts = [sys.argv[1]]                        # or your own: python 7a_try_prompts.py "Show me INC-0007"
    for prompt in prompts:
        print("USER:", prompt)
        r = run_with_tools(model, prompt, TOOLS, dispatch, confirm=ask_person)
        print("ANSWER:", r["answer"])
        print(f"[stopped={r['stopped']} | steps {r['steps']} | tool calls {len(r['tool_calls'])} | {money(r['cost_usd'])}]")
        print()
