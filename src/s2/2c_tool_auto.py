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
import re
from pydantic import field_validator
import anthropic

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

def error_text(e):
    # an answer that is not JSON has an empty field path, so call it "answer"
    return "; ".join(f"{'.'.join(map(str, x['loc'])) or 'answer'}: {x['msg']}" for x in e.errors())

TOOL = {"name": "record_incident",
        "description": "Record the fields extracted from one IT incident ticket.",
        "input_schema": IncidentExtract.model_json_schema()}              # 🔎 add "strict": True to guarantee the input matches the schema

TOOL_SYSTEM = SYSTEM + "\nYou must answer by calling the record_incident tool. Do not answer in prose."

def extract_via_tool(text):
    model = get_model_with_system_prompt(TOOL_SYSTEM)
    started = time.perf_counter()
    resp = model.ask([{"role": "user", "content": text}], max_tokens=2000,
                     tools=[TOOL], tool_choice={"type": "auto"})          # auto plus an instruction: a request, not a guarantee
    model.report(resp, time.perf_counter() - started)
    COSTS.append(model.cost_usd(resp.usage))
    return next((b for b in resp.content if b.type == "tool_use"), None)  # None means the model answered in prose

if __name__ == "__main__":
    try:                                                                  # step 1: the forced call this model rejects
        get_model_with_system_prompt(TOOL_SYSTEM).ask([{"role": "user", "content": TICKETS["t1"]}], max_tokens=2000,
                                     tools=[TOOL], tool_choice={"type": "tool", "name": "record_incident"})
    except anthropic.BadRequestError as e:
        print("forced tool_choice rejected:", e.message)
    for tid in (sys.argv[1:] or list(TICKETS)):                           # step 2: auto, then validate either way
        call = extract_via_tool(TICKETS[tid])
        if call is None:
            print(tid, "| PROSE: the model did not call the tool")
            continue
        try:
            IncidentExtract.model_validate(call.input)
            print(tid, "| tool call | valid")
        except ValidationError as e:
            print(tid, "| tool call | INVALID:", error_text(e))
    print(f"total cost ${sum(COSTS):.4f}")
