import asyncio, json, os, sys
from pathlib import Path
from mcp import Client, StdioServerParameters

# The smallest useful MCP client: start the 5a server as a subprocess, ask it which tools it has, then call one.
# This is what every host (VS Code, Claude Code, the Inspector) does when it connects: list first, call later.
#   python src/servicedesk/app.py                      (in another terminal: the tool calls this API)
#   python src/s4/5a_mcp_list_tools.py
# 5c_mcp_client.py goes further: it checks the schemas against servicedesk_tools.py and calls more tools.

HERE = Path(__file__).parent
SERVER = StdioServerParameters(command=sys.executable,                    # the same Python and virtual environment
                               args=[str(HERE / "5a_mcp_one_tool.py")],
                               env={"SERVICEDESK_URL": os.environ.get("SERVICEDESK_URL", "http://127.0.0.1:8000")})
                               # the server sees this, plus PATH and a few system variables: nothing else from here

async def main():
    async with Client(SERVER) as client:               # starts the server; stops it when the block ends
        # 1. Discover: what tools does this server offer?
        listing = await client.list_tools()
        print(f"tools on the server: {len(listing.tools)}")
        for tool in listing.tools:
            print()
            print("name:       ", tool.name)
            print("description:", tool.description)
            print("annotations:", tool.annotations)
            print("input_schema:")
            print(json.dumps(tool.input_schema, indent=2))

        # 2. Call: the same request a host sends when its model asks for this tool.
        args = {"service": "checkout", "status": "open", "limit": 3}
        print()
        print("call search_incidents", json.dumps(args))
        result = await client.call_tool("search_incidents", args)
        print("is_error:", result.is_error)            # a failed call is still a result, not an exception
        out = json.loads(result.content[0].text)       # the server sends dispatch()'s output as JSON text
        print(json.dumps(out, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
