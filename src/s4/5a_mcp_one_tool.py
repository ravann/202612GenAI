import json, sys
from typing import Annotated, Literal
from pydantic import Field
from mcp.server.mcpserver import MCPServer            # mcp 2.x. In mcp 1.x this class was FastMCP, in mcp.server.fastmcp
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from servicedesk_tools import TOOLS_BY_NAME, dispatch

# The smallest useful MCP server: one curated tool, search_incidents. It adds no tool logic of its own: the call
# goes through the same dispatch() as the model loop. 5b_mcp_server.py serves all six tools.
# An MCP client starts it as a subprocess and talks to it over stdin and stdout:
#   python src/s4/5c_mcp_client.py 5a_mcp_one_tool.py
#   or: npx @modelcontextprotocol/inspector@2.15.0 python src/s4/5a_mcp_one_tool.py
# Rule for stdio servers: stdout carries only protocol messages. Everything else goes to stderr.

def log(text):
    print("[compass-servicedesk]", text, file=sys.stderr)

def call(name, args):
    """One MCP tool call, sent through the same dispatcher the model loop uses."""
    sent = {}
    for key, value in args.items():
        if value is not None:                          # a parameter the client left out arrives as None: leave it out
            sent[key] = value
    out = dispatch(name, sent)
    log(f"{name} ok={out['ok']}")
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(out))], is_error=not out["ok"])

def about(tool, parameter):
    """The parameter's description in the tool layer, so MCP publishes the words the eval measured."""
    return Field(description=TOOLS_BY_NAME[tool]["input_schema"]["properties"][parameter]["description"])

# The SDK builds the tool's input schema from these type hints. Literal gives the schema an enum, with the same
# values as SERVICES, STATUSES and PRIORITIES in servicedesk_tools.py; Annotated adds each parameter's description.
Service = Literal["checkout", "crm", "payroll-portal", "vpn-gateway", "mail-relay", "printer-queue"]
Status = Literal["open", "in_progress", "resolved", "closed"]
Priority = Literal["P1", "P2", "P3", "P4"]

def search_incidents(service: Annotated[Service | None, about("search_incidents", "service")] = None,
                     status: Annotated[Status | None, about("search_incidents", "status")] = None,
                     priority: Annotated[Priority | None, about("search_incidents", "priority")] = None,
                     limit: Annotated[int | None, about("search_incidents", "limit")] = None):
    return call("search_incidents", {"service": service, "status": status, "priority": priority, "limit": limit})

server = MCPServer(name="compass-servicedesk")
server.add_tool(search_incidents, name="search_incidents", description=TOOLS_BY_NAME["search_incidents"]["description"],
                annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))

if __name__ == "__main__":
    log("serving 1 tool on stdio (this line goes to stderr)")
    server.run("stdio")
