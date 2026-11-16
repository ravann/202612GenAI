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

prompt = "Hello"

resp = ask([{"role": "user", "content": prompt}])
print(resp.content)       # raw: a list of typed blocks
print("---")
print(resp.usage)         # tokens in and out
