import anthropic
from dotenv import load_dotenv
from pathlib import Path

# The .env file is in code folder, one level up from this script
load_dotenv(Path(__file__).parent.parent / ".env")

client = anthropic.Anthropic()
MODEL = "claude-sonnet-5-5"                      # 🔎 confirm current model ID

# A long prefix that is identical on every call. Caching only applies above a minimum prefix length
# (🔎 check the current minimum for your model), so this runbook is deliberately large.
SERVICES = ["VPN", "SSO", "Email", "Wi-Fi", "Printing", "File shares", "Backup", "Patching", "Monitoring", "Ticketing",
            "Database", "Load balancer", "DNS", "DHCP", "Certificates", "Firewall", "Directory", "Storage", "Scheduler", "Mobile device management"]
CHECKS = ["confirm the alert is not a duplicate of an open incident", "check the service dashboard for the last 30 minutes",
          "look for a change record in the previous 24 hours", "verify the on-call engineer has acknowledged the page",
          "test from one internal and one external network", "review recent configuration changes in the audit log",
          "collect the exact error message and the affected user count", "check dependent services before restarting anything",
          "record the timeline in the incident ticket as you go", "decide whether this is a P1, P2 or P3 using the severity table"]

def build_runbook():
    lines = []
    for service in SERVICES:
        for n, check in enumerate(CHECKS, 1):
            lines.append(f"{service} runbook step {n}: {check}. If the {service} step fails twice, escalate to the {service} owner and note it in the ticket.")
    return "\n".join(lines)

RUNBOOK = build_runbook()

def ask_cached(question: str):
    return client.messages.create(
        model=MODEL, max_tokens=300,
        system=[{"type": "text",
                 "text": "You are Compass, an IT-operations assistant. Be concise. Use this runbook:\n" + RUNBOOK,
                 "cache_control": {"type": "ephemeral"}}],      # mark the end of the stable prefix
        messages=[{"role": "user", "content": question}])

def show_usage(label, usage):
    print(f"{label}: input={usage.input_tokens} cache_write={usage.cache_creation_input_tokens} "
          f"cache_read={usage.cache_read_input_tokens} output={usage.output_tokens}")

print(f"runbook: {len(RUNBOOK)} characters (roughly {len(RUNBOOK) // 4} tokens)")

resp = ask_cached("What is the first thing to check when VPN is down?")
show_usage("call 1 (writes the cache)", resp.usage)

resp = ask_cached("What is the first thing to check when email is slow?")
show_usage("call 2 (reads the cache)", resp.usage)
