# The Session 2 extractor as one reusable class (the finished version of the Session 2 exercise).
# It wraps a ModelAdapter and the IncidentExtract schema. Callers see one method: Extractor.extract(text) -> dict.
# Rule: no model name, prompt text or price is written in this file. They come from model.toml and prompts/*.md.
import re, time
from dataclasses import replace
from pathlib import Path
from typing import Literal
import anthropic
from anthropic import transform_schema
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from model_adapter import ModelAdapter, ModelConfig

PROMPTS = Path(__file__).parent / "prompts"
MAX_TOKENS = 2000        # thinking tokens count against max_tokens
MAX_REPAIRS = 2          # a cap: 1 first try plus at most 2 repairs
KNOWN_SERVICES = {"vpn-gateway", "payroll-portal", "mail-relay", "crm", "file-share", "printer-queue", "billing-db"}   # stands in for the CMDB (ServiceDesk arrives in Session 4)


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


def error_text(e):
    # an answer that is not JSON has an empty field path, so call it "answer"
    return "; ".join(f"{'.'.join(map(str, x['loc'])) or 'answer'}: {x['msg']}" for x in e.errors())


def parse(raw):
    """Validate the model's raw text at the boundary. Returns (IncidentExtract, None) or (None, error text)."""
    try:
        return IncidentExtract.model_validate_json(raw), None          # also catches text that is not JSON at all
    except ValidationError as e:
        return None, error_text(e)


def load_prompt(prompts_dir, version):
    text = (Path(prompts_dir) / f"{version}.md").read_text(encoding="utf-8")
    return text.split("---", 2)[2].strip()          # drop the front matter, keep the body


def review_reasons(data):
    """The semantic check: valid JSON is not the same as true. data is the dict from model_dump()."""
    reasons = []
    if data["service"] is not None and data["service"].lower() not in KNOWN_SERVICES:
        reasons.append(f"unknown service: {data['service']}")
    return reasons + data["ambiguity_notes"]


class Extractor:
    """Turns ticket text into a validated dict, or an explicit failure. One instance = one model + one prompt version.
    To compare two prompts or two models, make two instances. Callers see extract(); the model call stays in the adapter."""

    def __init__(self, config: ModelConfig, prompt="incident-v2", prompts_dir=PROMPTS, delimit=True, verbose=True):
        self.prompt_version = prompt
        self.delimit = delimit        # wrap the ticket in <ticket> tags (what incident-v2 expects)
        self.verbose = verbose        # False: no footer and no calls.jsonl line, for batch runs that keep their own report
        # the adapter takes its system prompt from the config: copy the config with this prompt, model.toml stays untouched
        self.adapter = ModelAdapter(replace(config, system=load_prompt(prompts_dir, prompt)))

    @staticmethod
    def wrap(text):
        # a delimiter the attacker can type is not a delimiter: remove the closing tag from the data first
        return f"<ticket>\n{text.replace('</ticket>', '')}\n</ticket>"

    def ask_once(self, content):
        """One structured call. Returns the raw API response."""
        started = time.perf_counter()
        resp = self.adapter.ask([{"role": "user", "content": content}],
                                max_tokens=MAX_TOKENS,
                                output_config={"format": {"type": "json_schema", "schema": transform_schema(IncidentExtract)}})
        if self.verbose:
            self.adapter.report(resp, time.perf_counter() - started)
        return resp

    def extract(self, text):
        """Always returns a dict with the same keys:
        ok          True if the answer passed validation
        data        the validated fields (dict), or None
        attempts    number of model calls made (1 = no repair)
        errors      one validation or API error per failed attempt (empty when the first try passed)
        reasons     why a human should look: unknown service, the model's ambiguity notes, the last error, or an unknown cost
        failure     None, "invalid" (cap reached, still invalid), "incomplete" (cut off or refused, not repaired)
                    or "api" (the API call itself failed)
        prompt      prompt version that produced this result
        model       model ID that produced it
        cost_usd    cost of all attempts together (thinking tokens included), or None if model.toml has no price for the model
        seconds     wall-clock time of all attempts together
        """
        started = time.perf_counter()
        r = {"ok": False, "data": None, "attempts": 0, "errors": [], "reasons": [], "failure": None,
             "prompt": self.prompt_version, "model": self.adapter.config.model, "cost_usd": 0.0, "seconds": 0.0}
        unpriced = False
        content = self.wrap(text) if self.delimit else text
        wrapped = content
        for attempt in range(1, MAX_REPAIRS + 2):
            r["attempts"] = attempt
            try:
                resp = self.ask_once(content)
            except anthropic.APIError as e:          # after the SDK's own retries; a quality failure is a different thing
                r["errors"].append(f"{type(e).__name__}: {e}")
                r["failure"] = "api"
                break
            try:
                r["cost_usd"] += self.adapter.cost_usd(resp.usage)
            except KeyError:                         # no price for this model: the call is billed, but its cost is unknown
                unpriced = True
            if resp.stop_reason in ("max_tokens", "refusal"):     # a cut-off or refused answer is not a prompt problem: no repair
                r["errors"].append(f"stop_reason={resp.stop_reason}: incomplete answer, not repaired")
                r["failure"] = "incomplete"
                break
            raw = self.adapter.text_of(resp)
            data, err = parse(raw)
            if data:
                r["ok"], r["data"] = True, data.model_dump()
                r["reasons"] = review_reasons(r["data"])
                break
            r["errors"].append(err)
            content = (f"{wrapped}\n\nYour previous answer was:\n{raw}\n"
                       f"It failed validation: {err}\n"
                       "Return a corrected answer. Use null where the text does not support a valid value.")
        if not r["ok"]:
            r["failure"] = r["failure"] or "invalid"          # fail visibly, never loop forever
            r["reasons"] = r["errors"][-1:]
        if unpriced:
            r["cost_usd"] = None
            r["reasons"].append(f"cost unknown: add {r['model']} to [prices]")
        r["seconds"] = time.perf_counter() - started
        return r
