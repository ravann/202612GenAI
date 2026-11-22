import json, sys, time
from dataclasses import replace
from pathlib import Path
from dotenv import load_dotenv
from model_adapter import ModelAdapter, ModelConfig

CYAN, RESET = "\033[36m", "\033[0m"      # ANSI escape codes; work in most terminals

# The .env file is in the code folder, one level up from this script
load_dotenv(Path(__file__).parent.parent / ".env")

HERE = Path(__file__).parent
CONFIG = ModelConfig.load(HERE / "model.toml")
TICKETS = {t["id"]: t["text"] for t in map(json.loads, open(HERE / "tickets.jsonl", encoding="utf-8"))}

def get_model_with_system_prompt(system):
    # the adapter takes its system prompt from the config: copy the config with this prompt, no adapter edit
    return ModelAdapter(replace(CONFIG, system=system))

VAGUE = "Summarize this IT ticket."
CONTRACT = """You extract fields from IT incident tickets.
Rules:
- Use only what the text states. If a field is absent, write null. Never guess.
- Never invent ticket IDs, service names or priorities.
Output exactly three lines and nothing else:
ticket_id: <ID or null>
service: <service name or null>
priority: <P1, P2, P3, P4 or null>"""

def run(system, text, n=3):
    model = get_model_with_system_prompt(system)
    for i in range(n):
        started = time.perf_counter()
        resp = model.ask([{"role": "user", "content": text}], max_tokens=1000)    # room for thinking tokens
        print(f"{CYAN}--- run {i + 1}{RESET}")
        print(model.text_of(resp))
        model.report(resp, time.perf_counter() - started)                       # footer and calls.jsonl line, as in Session 1

if __name__ == "__main__":
    print(f"{CYAN}== vague prompt{RESET}")
    run(VAGUE, TICKETS["t3"])
    print(f"{CYAN}== output contract{RESET}")
    run(CONTRACT, TICKETS["t3"])
