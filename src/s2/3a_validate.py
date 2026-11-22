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

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from anthropic import transform_schema
import re
from pydantic import field_validator

class IncidentExtract(BaseModel):
    model_config = ConfigDict(extra="forbid")      # an unknown key is an error, and the JSON schema says additionalProperties: false
    ticket_id: str | None = Field(description="Ticket ID exactly as written, like INC-1234. null if the text has none.")
    service: str | None = Field(description="Service name exactly as written. null if the text names none.")
    priority: Literal["P1", "P2", "P3", "P4"] | None = Field(description="Priority if the text states one. null if not.")
    summary: str = Field(description="One sentence, at most 25 words.")
    ambiguity_notes: list[str] = Field(description="Contradictions or unclear points. Empty list if none.")

    @field_validator("ticket_id")
    @classmethod
    def id_format(cls, v):
        if v is not None and not re.fullmatch(r"INC-\d{4}", v):        # a business rule we keep in code, on purpose
            raise ValueError("ticket_id must look like INC-1234, or be null if the text has no such ID")
        return v

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

def error_text(e):
    # an answer that is not JSON has an empty field path, so call it "answer"
    return "; ".join(f"{'.'.join(map(str, x['loc'])) or 'answer'}: {x['msg']}" for x in e.errors())

def parse(raw):
    try:
        return IncidentExtract.model_validate_json(raw), None          # also catches text that is not JSON at all
    except ValidationError as e:
        return None, error_text(e)

if __name__ == "__main__":
    bad = '{"ticket_id": "INC-77", "service": null, "priority": "P3", "summary": "x", "ambiguity_notes": []}'
    (res, err) = parse(bad)
    print(f"{CYAN}--- bad ticket {RESET}")
    print((err))                          # offline: no API call
    not_json = "not JSON at all"
    (res, err) = parse(not_json)
    print(f"{CYAN}--- not JSON {RESET}")
    print((err))                          # offline: no API call
    for tid in ["t1", "t5"]:
        ticket_parsed_raw = extract_once(TICKETS[tid])
        (data, err) = parse(ticket_parsed_raw)
        print(f"{CYAN}--- {tid}{RESET}")
        print(json.dumps(ticket_parsed_raw, indent=2))
        print("valid" if data else f"INVALID: {err}")
