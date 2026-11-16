# Exercise: move the extractor steps of Session 2 (5b_extractor.py / 7b_delimiters.py) into this class.
# main.py, model.toml, model_adapter.py, tickets.jsonl and prompts/ are finished. Fill in every TODO until
# `python main.py` prints one line per ticket.
# Rule: no model name, prompt text or price may be written in this file. They come from model.toml and prompts/*.md.
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
        # TODO 1: same rule as the validator in 3a_validate.py: a ticket_id must look like INC-1234 (four digits),
        # or be null. Raise ValueError with a message the model can act on. Return v when it is valid.
        raise NotImplementedError


def error_text(e):
    # TODO 2: same as error_text() in 3a_validate.py: one short line from a ValidationError (field path and message).
    raise NotImplementedError


def parse(raw):
    """Validate the model's raw text at the boundary. Returns (IncidentExtract, None) or (None, error text)."""
    # TODO 3: same as parse() in 3a_validate.py.
    raise NotImplementedError


def load_prompt(prompts_dir, version):
    # TODO 4: same as load_prompt() in 5a_prompt_files.py, but read prompts_dir / f"{version}.md".
    # Return the body only (drop the front matter).
    raise NotImplementedError


def review_reasons(data):
    """The semantic check: valid JSON is not the same as true. data is the dict from model_dump()."""
    # TODO 5: same as review_reasons() in 5b_extractor.py.
    # An unknown service becomes a reason; the model's own ambiguity_notes are added after it.
    raise NotImplementedError


class Extractor:
    """Turns ticket text into a validated dict, or an explicit failure. One instance = one model + one prompt version.
    To compare two prompts or two models, make two instances. Callers see extract(); the model call stays in the adapter."""

    def __init__(self, config: ModelConfig, prompt="incident-v2", prompts_dir=PROMPTS, delimit=True, verbose=True):
        # TODO 6: keep prompt, delimit and verbose. Build self.adapter: copy the config with the prompt text as its
        # system prompt (dataclasses.replace, as get_model_with_system_prompt() did in the step scripts) and wrap it in a
        # ModelAdapter.
        # delimit: wrap the ticket in <ticket> tags (what incident-v2 expects).
        # verbose: False means no footer and no calls.jsonl line, for batch runs that keep their own report.
        raise NotImplementedError

    @staticmethod
    def wrap(text):
        # TODO 7: same as wrap() in 7b_delimiters.py: put the text inside <ticket> tags and remove any closing tag
        # that is already in the text.
        raise NotImplementedError

    def ask_once(self, content):
        """One structured call. Returns the raw API response."""
        # TODO 8: same as extract_once() in 2b_structured_call.py, using self.adapter. Time the call, ask with
        # max_tokens=MAX_TOKENS and the output_config argument, and print the footer only if self.verbose.
        # Return resp (not the text): extract() needs resp.usage and resp.stop_reason.
        raise NotImplementedError

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
        # TODO 9: the capped repair loop from 3b_repair_loop.py, using the methods above:
        #   - wrap the text if self.delimit; call ask_once; validate the answer with parse()
        #   - valid: set ok and data (data.model_dump()) and reasons (review_reasons), stop
        #   - invalid: record the error and send a repair message (the wrapped text, the previous answer, the error and
        #     "Return a corrected answer. Use null where the text does not support a valid value."), at most MAX_REPAIRS times
        #   - a stop_reason of "max_tokens" or "refusal": record it in errors, failure = "incomplete", stop
        #     (a cut-off or refused answer is not a prompt problem, so a repair would not help)
        #   - catch anthropic.APIError: failure = "api", stop. After the cap: failure = "invalid", reasons = the last error
        #   - add up cost_usd (self.adapter.cost_usd) and seconds over all attempts. A model with no price in model.toml
        #     raises KeyError there: the call is still billed, so set cost_usd to None and add the reason
        #     "cost unknown: add <model> to [prices]" (model.toml prices claude-sonnet-5-5, claude-haiku-5-5 and Haiku 4.5)
        raise NotImplementedError
