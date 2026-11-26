import asyncio, json, os, sys
from pathlib import Path
from mcp import Client, StdioServerParameters
from servicedesk_tools import TOOLS_BY_NAME

# A small MCP client: it starts the server as a subprocess, lists its tools and calls some of them.
# This is what a host (VS Code, Claude Code, the Inspector) does when it connects to the server.
# The server writes only if the host is trusted to confirm: COMPASS_HOST_CONFIRMS=1 before you run this script.

HERE = Path(__file__).parent
SCRIPT = "mcp_server.py"
if len(sys.argv) > 1:
    SCRIPT = sys.argv[1]                               # another server: python 5c_mcp_client.py 5a_mcp_one_tool.py
SERVER = StdioServerParameters(command=sys.executable,                     # the same Python and virtual environment
                               args=[str(HERE / SCRIPT)],
                               env={"SERVICEDESK_URL": os.environ.get("SERVICEDESK_URL", "http://127.0.0.1:8000"),
                                    "COMPASS_HOST_CONFIRMS": os.environ.get("COMPASS_HOST_CONFIRMS", "0"),
                                    "PYTHONDONTWRITEBYTECODE": "1"})       # the server sees these, plus PATH and a few
                                                                           # system variables: nothing else from here
CALLS = [("search_incidents", {"service": "checkout", "priority": "P1"}),
         ("get_asset_dependencies", {"asset_id": "db-04"}),
         ("get_incident", {"incident_id": "INC-9999"}),                    # an error is a result, with is_error=True
         ("search_incidents", {"status": "urgent"}),                       # the server's schema refuses it first
         ("approve_change", {"change_id": "CHG-0003"})]                    # hidden: not on the server at all
for incident_id in ["INC-0031", "INC-0033", "INC-0034", "INC-0041"]:       # four writes: refused unless the host is
    CALLS.append(("assign_incident", {"incident_id": incident_id, "assignee": "dave"}))   # trusted; the 4th hits the cap

def parameters(schema):
    """Parameter names, with the required ones marked by *."""
    names = []
    for name in schema["properties"]:
        if name in schema.get("required", []):
            names.append(name + "*")
        else:
            names.append(name)
    return names

def allowed(prop):
    """A parameter's enum, or None. The SDK puts an optional parameter's enum inside anyOf (the value, or null)."""
    if "enum" in prop:
        return prop["enum"]
    for option in prop.get("anyOf", []):
        if "enum" in option:
            return option["enum"]
    return None

def differences(published, ours):
    """Where the server's schema differs from servicedesk_tools.py: parameter names, descriptions or enums."""
    found = []
    if parameters(published) != parameters(ours):
        found.append("parameters")
    for name, prop in ours["properties"].items():
        theirs = published["properties"].get(name, {})
        if theirs.get("description") != prop.get("description"):
            found.append(name + " description")
        if allowed(theirs) != allowed(prop):
            found.append(name + " enum")
    return found

# The MCP SDK is asynchronous. "async def" marks a function that can wait for the server without blocking,
# and "await" marks each place where it waits. asyncio.run(main()) at the bottom runs it to the end.
async def main():
    async with Client(SERVER) as client:               # starts the server; stops it when the block ends
        listing = await client.list_tools()
        print(f"tools on the server: {len(listing.tools)} (* = required parameter)")
        drift = 0
        for tool in listing.tools:
            read_only = "?"                            # no annotations: the host is told nothing
            if tool.annotations is not None:
                read_only = str(tool.annotations.read_only_hint)      # a hint for the host: does this tool change data?
            print(f"  {tool.name:23} read_only={read_only:5}  {', '.join(parameters(tool.input_schema))}")
            found = differences(tool.input_schema, TOOLS_BY_NAME[tool.name]["input_schema"])
            if found:                                  # two definitions of one tool must not drift apart
                drift += 1
                print("    NOT THE SAME AS servicedesk_tools.py:", ", ".join(found))
        print(f"tools that differ from servicedesk_tools.py (names, required, descriptions, enums): {drift}")
        first = listing.tools[0]                       # what a host's model reads about each parameter of one tool
        for name, prop in first.input_schema["properties"].items():
            print(f"  {first.name}.{name}: {prop.get('description')}")
        print()
        for name, args in CALLS:
            result = await client.call_tool(name, args)
            print(f"call {name} {json.dumps(args)} -> is_error={result.is_error}")
            text = result.content[0].text
            if len(text) > 160:
                text = text[:160] + "..."
            print("  ", text)

if __name__ == "__main__":
    asyncio.run(main())
