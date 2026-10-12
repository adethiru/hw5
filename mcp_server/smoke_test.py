"""MCP smoke test over the real MCP protocol (stdio), no LLM.

    .venv/bin/python mcp_server/smoke_test.py

Starts mcp_server/server.py exactly the way .mcp.json does, connects an MCP
client (official `mcp` Python SDK), lists the tools, calls the three Problem 3
tools and writes the raw results to output/mcp_smoke.json. Used when Claude
Code is not available; the file records which client produced it.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server" / "server.py"
OUT = ROOT / "output" / "mcp_smoke.json"

TESTS = [
    ("How many CC-HOOD-NAVY size M hoodies are on hand for ticket 103, which needs 20?",
     "check_inventory_stock", {"sku": "CC-HOOD-NAVY", "size": "M", "qty_needed": 20}),
    ("What is Bulldog Print Co (vendor 1) status - lead time, open invoices, will it ship?",
     "check_vendor_status", {"vendor_id": 1}),
    ("What rent is due on lease 1 for ticket 102?",
     "get_lease_rent_status", {"lease_id": 1}),
]


def _payload(result) -> object:
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict):
        return sc["result"] if set(sc) == {"result"} else sc
    for block in result.content or []:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    return None


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = sorted(t.name for t in (await session.list_tools()).tools)
            tests = []
            for prompt, tool, args in TESTS:
                res = await session.call_tool(tool, args)
                tests.append({"prompt": prompt, "tool": tool, "arguments": args,
                              "is_error": bool(getattr(res, "isError", False)),
                              "tool_output": _payload(res)})
                print(f"✓ {tool}({args})")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "client": "MCP Python SDK stdio client (mcp_server/smoke_test.py) - fallback because Claude Code was not available",
        "mcp_server": "campus-customs (" + getattr(init.serverInfo, "name", "campus-customs") + ")",
        "connection": "stdio: .venv/bin/python mcp_server/server.py (same command as .mcp.json)",
        "database": "data/campus_customs_new.db",
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tools_listed": tools,
        "tests": tests,
    }, indent=2) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(tools)} tools listed)")


if __name__ == "__main__":
    asyncio.run(main())
