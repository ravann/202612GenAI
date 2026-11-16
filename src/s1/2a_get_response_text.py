import sys
import anthropic
from dotenv import load_dotenv
from pathlib import Path

# The .env file is in code folder, one level up from this script
load_dotenv(Path(__file__).parent.parent / ".env")

client = anthropic.Anthropic()
MODEL = "claude-sonnet-5-5"                      # 🔎 confirm current model ID
SYSTEM = "You are Compass, an IT-operations assistant. Be concise. If you do not know, say so."

def ask(messages):
    resp = client.messages.create(model=MODEL, 
                                  max_tokens=500, 
                                  system=SYSTEM, 
                                  messages=messages)
    return resp

def text_of(resp):
    # thinking blocks come BEFORE text, so resp.content[0].text can raise or return the wrong block
    return "".join(b.text for b in resp.content if b.type == "text")

prompt = "Hello"

resp = ask([{"role": "user", "content": prompt}])
print(text_of(resp))
