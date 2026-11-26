import json, os, sys
from typing import Annotated, Literal
from pydantic import Field
from mcp.server.mcpserver import MCPServer            # mcp 2.x. In mcp 1.x this class was FastMCP, in mcp.server.fastmcp
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from servicedesk_tools import RULES, TOOLS_BY_NAME, dispatch, error

# A local MCP server for the six curated tools. It adds no tool logic of its own: every call goes through the same
# dispatch() as the model loop, so validation, scopes, confirmation and errors are the same over MCP.
# Two rules no client can get around: a write is refused unless you declare the host trusted, and the server
# runs at most MAX_WRITES writes and proposals in one run.
# An MCP client starts it as a subprocess and talks to it over stdin and stdout:
#   python src/s4/5c_mcp_client.py
#   or: npx @modelcontextprotocol/inspector@2.15.0 python src/s4/mcp_server.py
# Rule for stdio servers: stdout carries only protocol messages. Everything else goes to stderr.

HOST_CONFIRMS = os.environ.get("COMPASS_HOST_CONFIRMS") == "1"   # 1 only for a host that shows every call to a person
MAX_WRITES = 3                                                   # writes and proposals per server run
WRITES = {"done": 0}                                             # a dict, so call() can change the count

def log(text):
    print("[compass-servicedesk]", text, file=sys.stderr)

def confirmed_by_host(name, args):
    # The server cannot see whether a person approved the call. It trusts the host only when you say so.
    return HOST_CONFIRMS

def call(name, args):
    """One MCP tool call, sent through the same dispatcher the model loop uses."""
    sent = {}
    for key, value in args.items():
        if value is not None:                          # a parameter the client left out arrives as None: leave it out
            sent[key] = value
    is_write = RULES[name]["risk"] != "read"           # a write or a proposal
    if is_write:
        WRITES["done"] += 1                            # counted in the server, so no client can reset it
    if is_write and WRITES["done"] > MAX_WRITES:
        out = error("too_many_writes", f"More than {MAX_WRITES} write attempts in this server run",
                    "Stop and tell the user; a person must restart the server to allow more")
    else:
        out = dispatch(name, sent, confirm=confirmed_by_host)
    log(f"{name} ok={out['ok']}")
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(out))], is_error=not out["ok"])

def about(tool, parameter):
    """The parameter's description in the tool layer, so MCP publishes the words the eval measured."""
    return Field(description=TOOLS_BY_NAME[tool]["input_schema"]["properties"][parameter]["description"])

# The SDK builds each tool's input schema from these type hints. Literal gives the schema an enum, with the same
# values as in servicedesk_tools.py; Annotated adds each parameter's description from there. Patterns and bounds
# (the ID formats, limit at most 20) are not published: dispatch() checks them and answers with the tool's hint.
Service = Literal["checkout", "crm", "payroll-portal", "vpn-gateway", "mail-relay", "printer-queue"]
AssetService = Literal["checkout", "crm", "payroll-portal", "vpn-gateway", "mail-relay", "printer-queue", "shared-infra"]
Status = Literal["open", "in_progress", "resolved", "closed"]
Priority = Literal["P1", "P2", "P3", "P4"]
Risk = Literal["low", "medium", "high"]
Engineer = Literal["bob", "dave", "erin"]

# One small function per tool: its parameters are the tool's parameters, and its body hands them to call().
def search_incidents(service: Annotated[Service | None, about("search_incidents", "service")] = None,
                     status: Annotated[Status | None, about("search_incidents", "status")] = None,
                     priority: Annotated[Priority | None, about("search_incidents", "priority")] = None,
                     limit: Annotated[int | None, about("search_incidents", "limit")] = None):
    return call("search_incidents", {"service": service, "status": status, "priority": priority, "limit": limit})

def get_incident(incident_id: Annotated[str, about("get_incident", "incident_id")]):
    return call("get_incident", {"incident_id": incident_id})

def find_asset(query: Annotated[str, about("find_asset", "query")],
               service: Annotated[AssetService | None, about("find_asset", "service")] = None):
    return call("find_asset", {"query": query, "service": service})

def get_asset_dependencies(asset_id: Annotated[str, about("get_asset_dependencies", "asset_id")]):
    return call("get_asset_dependencies", {"asset_id": asset_id})

def assign_incident(incident_id: Annotated[str, about("assign_incident", "incident_id")],
                    assignee: Annotated[Engineer, about("assign_incident", "assignee")]):
    return call("assign_incident", {"incident_id": incident_id, "assignee": assignee})

def propose_change_request(title: Annotated[str, about("propose_change_request", "title")],
                           description: Annotated[str, about("propose_change_request", "description")],
                           service: Annotated[Service, about("propose_change_request", "service")],
                           risk: Annotated[Risk, about("propose_change_request", "risk")],
                           asset_ids: Annotated[list[str] | None, about("propose_change_request", "asset_ids")] = None,
                           related_incident: Annotated[str | None,
                                                       about("propose_change_request", "related_incident")] = None,
                           rollback_plan: Annotated[str | None, about("propose_change_request", "rollback_plan")] = None):
    return call("propose_change_request", {"title": title, "description": description, "service": service, "risk": risk,
                                           "asset_ids": asset_ids, "related_incident": related_incident,
                                           "rollback_plan": rollback_plan})

# Annotations are hints for the host, not controls: the server enforces the rules above whatever the host does.
READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
ASSIGN = ToolAnnotations(read_only_hint=False, destructive_hint=True,      # it overwrites the previous assignee
                         idempotent_hint=True, open_world_hint=False)
PROPOSE = ToolAnnotations(read_only_hint=False, destructive_hint=False,    # it only adds a pending change
                          idempotent_hint=True, open_world_hint=False)     # idempotent for identical arguments only

SIX_TOOLS = [("search_incidents", search_incidents, READ),
             ("get_incident", get_incident, READ),
             ("find_asset", find_asset, READ),
             ("get_asset_dependencies", get_asset_dependencies, READ),
             ("assign_incident", assign_incident, ASSIGN),
             ("propose_change_request", propose_change_request, PROPOSE)]

server = MCPServer(name="compass-servicedesk")
for name, function, annotations in SIX_TOOLS:          # the description is the curated one: the same words the model reads
    server.add_tool(function, name=name, description=TOOLS_BY_NAME[name]["description"], annotations=annotations)

if __name__ == "__main__":
    log(f"serving 6 tools on stdio; host trusted to confirm writes: {HOST_CONFIRMS} (this line goes to stderr)")
    server.run("stdio")
