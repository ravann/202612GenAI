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

def load_prompt(version):
    text = (HERE / "prompts" / f"{version}.md").read_text(encoding="utf-8")
    return text.split("---", 2)[2].strip()          # drop the front matter, keep the body

PROMPT_VERSION = "incident-v1"
SYSTEM = load_prompt(PROMPT_VERSION)

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

COSTS = []                                          # cost of every call, for a totals line later

def extract_once(content, system=SYSTEM, effort=None, **options):
    model = get_model_with_system_prompt(system)
    output_config = {"format": {"type": "json_schema", "schema": transform_schema(IncidentExtract)}}
    if effort:
        output_config["effort"] = effort               # low, medium, high (the default on Sonnet 5.5), xhigh or max
    started = time.perf_counter()
    resp = model.ask([{"role": "user", "content": content}],
                     max_tokens=2000,                  # thinking tokens count against this
                     output_config=output_config,
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

MAX_REPAIRS = 2                                # a cap: 1 first try plus at most 2 repairs

def extract(text):
    content = text
    for attempt in range(1, MAX_REPAIRS + 2):
        raw = extract_once(content)
        data, err = parse(raw)
        if data:
            return {"ok": True, "data": data.model_dump(), "attempts": attempt, "prompt": PROMPT_VERSION}
        print(f"  attempt {attempt} failed: {err}")
        content = (f"{text}\n\nYour previous answer was:\n{raw}\n"
                   f"It failed validation: {err}\n"
                   "Return a corrected answer. Use null where the text does not support a valid value.")
    return {"ok": False, "error": err, "attempts": attempt, "prompt": PROMPT_VERSION}   # fail visibly, never loop forever

KNOWN_SERVICES = {"vpn-gateway", "payroll-portal", "mail-relay", "crm", "file-share", "printer-queue", "billing-db"}   # stands in for the CMDB (ServiceDesk arrives in Session 4)

def review_reasons(data):
    reasons = []
    if data["service"] is not None and data["service"].lower() not in KNOWN_SERVICES:
        reasons.append(f"unknown service: {data['service']}")         # valid JSON is not the same as true
    return reasons + data["ambiguity_notes"]

def main():
    ids = sys.argv[1:] or list(TICKETS)                                 # optional: python 6_extractor.py t1 t5
    for tid in ids:
        r = extract(TICKETS[tid])
        reasons = review_reasons(r["data"]) if r["ok"] else [r["error"]]
        print(f"{tid} | ok={r['ok']} | attempts={r['attempts']} | prompt={r['prompt']} | needs_review={bool(reasons)}")
        print(f"    data={r.get('data')}\n    reasons={reasons}")
    print(f"total cost ${sum(COSTS):.4f}")

if __name__ == "__main__":
    main()
