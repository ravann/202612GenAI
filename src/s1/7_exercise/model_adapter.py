# Exercise: move the model-calling code of the Session 1 Compass (6_compass.py) into this class.
# main.py and model.toml are finished. Fill in every TODO until `python main.py` chats like 6_compass.py did.
# Rule: no model name, number, prompt or price may be written in this file. They all come from `self.config`.
import json, time, tomllib
from dataclasses import dataclass
import anthropic


@dataclass(frozen=True)
class ModelConfig:
    model: str
    system: str
    max_tokens: int
    timeout: float
    max_retries: int
    log_path: str
    prices: dict          # model -> (USD per million input tokens, USD per million output tokens)

    @classmethod
    def load(cls, path):
        # TODO 1: read the TOML file with tomllib (open it in "rb" mode), turn each price list into a tuple,
        # and return cls(**data).
        raise NotImplementedError


class ModelAdapter:
    """The only code that talks to the model. Callers see ask, ask_stream and report, so the provider behind them can change. The chat loop and the history stay in the caller."""

    def __init__(self, config: ModelConfig):
        # TODO 2: keep the config, and create the Anthropic client with the config's timeout and max_retries.
        raise NotImplementedError

    @staticmethod
    def text_of(resp):
        # TODO 3: same as text_of in 6_compass.py (join the text blocks only).
        raise NotImplementedError

    def ask(self, messages, max_tokens=None, stop=None, **options):
        # TODO 4: same as ask() in 6_compass.py. Use the config's model, system prompt and default max_tokens,
        # and pass **options on to messages.create (Session 2 passes tools this way).
        raise NotImplementedError

    def ask_stream(self, messages, on_text=None):
        # TODO 5: same as ask_stream() in 6_compass.py, but do not print. Call on_text(chunk) if it is given.
        # Return (resp, ttft).
        raise NotImplementedError

    def safe_stream(self, messages, on_text=None):
        # TODO 6: same as safe_chat_turn() in 6_compass.py, calling self.ask_stream. Return None after an error.
        raise NotImplementedError

    def cost_usd(self, usage):
        # TODO 7: same as cost_usd() in 6_compass.py, with the prices from the config.
        raise NotImplementedError

    def report(self, resp, seconds, ttft=None):
        # TODO 8: same as report() in 6_compass.py. Model and log path come from the config.
        raise NotImplementedError
