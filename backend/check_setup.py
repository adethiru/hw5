"""Offline setup check - makes NO model calls (zero tokens).

    python -m backend.check_setup

Starts the MCP server, lists its tools, and shows each agent's filtered
toolset so you can confirm least-privilege wiring and the model name.
"""

import asyncio

from backend.config import MODEL_NAME, WORKING_DB
from backend.mcp_client import HUMAN_ONLY_TOOLS, ROLE_TOOLS, build_mcp_server


async def main() -> None:
    print(f"Model: {MODEL_NAME}\nWorking DB: {WORKING_DB} (exists={WORKING_DB.exists()})")
    server = build_mcp_server()
    async with server:
        tools = sorted(t.name for t in await server.list_tools())
    print(f"\nMCP server exposes {len(tools)} tools:\n  " + "\n  ".join(tools))
    missing = {t for r in ROLE_TOOLS.values() for t in r} - set(tools)
    print("\nRole tools missing from server:", missing or "none")
    for role, allowed in ROLE_TOOLS.items():
        print(f"\n{role}: {sorted(allowed - HUMAN_ONLY_TOOLS)} + delegate_task")
    print(f"\nHuman-only (hidden from all agents): {sorted(HUMAN_ONLY_TOOLS)}")


if __name__ == "__main__":
    asyncio.run(main())
