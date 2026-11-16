import sys
import anthropic
from dotenv import load_dotenv
from pathlib import Path

# The .env file is in code folder, one level up from this script
load_dotenv(Path(__file__).parent.parent / ".env")

client = anthropic.Anthropic()
MODEL = "claude-sonnet-5-5"                      # 🔎 confirm current model ID
SYSTEM = "You are Compass, an IT-operations assistant. Be concise. If you do not know, say so."

def ask(messages: list, max_tokens: int = 500, stop=None):
    resp = client.messages.create(model=MODEL, 
                                  max_tokens=max_tokens, 
                                  system=SYSTEM, 
                                  messages=messages,
                                  stop_sequences=stop or [])
    return resp

def text_of(resp):
    # thinking blocks come BEFORE text, so resp.content[0].text can raise or return the wrong block
    return "".join(b.text for b in resp.content if b.type == "text")

prompt = "List 5 common causes of VPN failure."

resp = ask([{"role": "user", "content": prompt}], max_tokens=3000)
print(text_of(resp))
print("stop:", resp.stop_reason)
print("---")
resp = ask([{"role": "user", "content": prompt}], max_tokens=100)
print(text_of(resp))
print("stop:", resp.stop_reason)
