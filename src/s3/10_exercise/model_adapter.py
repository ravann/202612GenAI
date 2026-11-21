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
        with open(path, "rb") as f:
            data = tomllib.load(f)
        data["prices"] = {m: tuple(p) for m, p in data["prices"].items()}
        return cls(**data)                      # a missing or misspelled key is a TypeError: loud, on purpose


class ModelAdapter:
    """The only code that talks to the model. Callers see ask, ask_stream and report, so the provider behind them can change. The chat loop and the history stay in the caller."""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.client = anthropic.Anthropic(timeout=config.timeout, max_retries=config.max_retries)

    @staticmethod
    def text_of(resp):
        # thinking blocks come BEFORE text, so resp.content[0].text can raise or return the wrong block
        return "".join(b.text for b in resp.content if b.type == "text")

    def ask(self, messages, max_tokens=None, stop=None, **options):
        c = self.config
        return self.client.messages.create(model=c.model,
                                           max_tokens=max_tokens or c.max_tokens,
                                           system=c.system,
                                           messages=messages,
                                           stop_sequences=stop or [],
                                           **options)     # e.g. tools=..., used from Session 2

    def ask_stream(self, messages, on_text=None):
        c = self.config
        started, ttft = time.perf_counter(), None
        with self.client.messages.stream(model=c.model, max_tokens=c.max_tokens,
                                         system=c.system, messages=messages) as stream:
            for chunk in stream.text_stream:
                if ttft is None:
                    ttft = time.perf_counter() - started      # what the user feels as "it started"
                if on_text:
                    on_text(chunk)
            resp = stream.get_final_message()                 # usage exists only once the stream ends
        return resp, ttft

    def safe_stream(self, messages, on_text=None):
        """Like ask_stream, but prints a classified error and returns None instead of raising."""
        try:
            return self.ask_stream(messages, on_text)
        except anthropic.APIStatusError as e:                     # the server answered with an error status
            body = e.body if isinstance(e.body, dict) else {}
            err = body.get("error", body)
            kind = err.get("type", "") if isinstance(err, dict) else ""
            if e.status_code == 200:                              # an error event mid-stream arrives on an HTTP 200
                transient = kind in ("overloaded_error", "api_error", "rate_limit_error")
            else:
                transient = e.status_code in (408, 409, 429) or e.status_code >= 500
            hints = {401: "check ANTHROPIC_API_KEY", 403: "key lacks permission", 404: "check the model ID",
                     413: "request too large, shorten the history"}
            advice = "transient, retries used up" if transient else hints.get(e.status_code, "fix the request, do not retry")
            print(f"\n[error {f'{e.status_code} {kind}'.strip()}: {advice}]")
        except anthropic.APIConnectionError:                      # includes timeouts
            print("\n[connection or timeout error, retries used up]")
        except KeyboardInterrupt:                                 # Ctrl+C mid-stream: drop the partial answer
            print("\n[interrupted]")
        return None

    def cost_usd(self, usage):
        price_in, price_out = self.config.prices[self.config.model]   # a missing price is a KeyError: loud, on purpose
        return (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000

    def report(self, resp, seconds, ttft=None):        # ttft (time to first token) exists only for streamed calls
        try:
            cost = self.cost_usd(resp.usage)
            shown = f"${cost:.5f}"
        except KeyError:                               # no price for the model: still log the billed call, with the cost unknown
            cost, shown = None, f"cost unknown: add {self.config.model} to [prices]"
        first = f" | ttft {ttft:.2f}s" if ttft is not None else ""
        print(f"[{resp.usage.input_tokens} in / {resp.usage.output_tokens} out | {seconds:.2f}s{first} | {shown} | {resp.stop_reason}]")
        with open(self.config.log_path, "a") as f:     # metadata only: never the prompt text, never a key
            f.write(json.dumps({"ts": time.time(), 
                                "model": self.config.model, 
                                "in": resp.usage.input_tokens,
                                "out": resp.usage.output_tokens, 
                                "seconds": round(seconds, 3),
                                "ttft": None if ttft is None else round(ttft, 3),
                                "cost_usd": cost, 
                                "stop": resp.stop_reason}) + "\n"
                    )
