import json, sys, time
from dataclasses import replace
from pathlib import Path
from dotenv import load_dotenv
from model_adapter import ModelAdapter, ModelConfig

# The .env file is in the code folder, one level up from this script
load_dotenv(Path(__file__).parent.parent / ".env")

HERE = Path(__file__).parent
CONFIG = ModelConfig.load(HERE / "model.toml")
TICKETS = {t["id"]: t["text"] for t in map(json.loads, open(HERE / "tickets.jsonl", encoding="utf-8"))}

def get_model_with_system_prompt(system):
    # the adapter takes its system prompt from the config: copy the config with this prompt, no adapter edit
    return ModelAdapter(replace(CONFIG, system=system))

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from anthropic import transform_schema

class IncidentExtract(BaseModel):
    model_config = ConfigDict(extra="forbid")      # an unknown key is an error, and the JSON schema says additionalProperties: false
    ticket_id: str | None = Field(description="Ticket ID exactly as written, like INC-1234. null if the text has none.")
    service: str | None = Field(description="Service name exactly as written. null if the text names none.")
    priority: Literal["P1", "P2", "P3", "P4"] | None = Field(description="Priority if the text states one. null if not.")
    summary: str = Field(description="One sentence, at most 25 words.")
    ambiguity_notes: list[str] = Field(description="Contradictions or unclear points. Empty list if none.")

SYSTEM = """You extract fields from IT incident tickets.
Rules:
- Use only what the text states. If a field is absent, use null. Never guess.
- Never invent ticket IDs, service names or priorities.
- Put contradictions or unclear points in ambiguity_notes."""

COSTS = []                                          # cost of every call, for a totals line later

def extract_once(content, system=SYSTEM, **options):
    model = get_model_with_system_prompt(system)
    started = time.perf_counter()
    resp = model.ask([{"role": "user", "content": content}],
                     max_tokens=2000,                  # thinking tokens count against this
                     output_config={"format": {"type": "json_schema", "schema": transform_schema(IncidentExtract)}},
                     **options)
    model.report(resp, time.perf_counter() - started)
    COSTS.append(model.cost_usd(resp.usage))
    return model.text_of(resp)                         # the JSON arrives as a text block

if __name__ == "__main__":
    raw = extract_once(TICKETS["t1"])
    print(raw)                                                    # the raw text, before any parsing
    print(json.dumps(json.loads(raw), indent=2))
