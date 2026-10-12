"""Connects the agent team to the Campus Customs MCP server.

All shop facts and actions go through MCP - there is no second tools layer.
Each agent gets a *filtered view* of the same MCP server (least privilege),
and human-only tools are removed from every agent.
"""

from __future__ import annotations

import sys

from pydantic_ai.mcp import MCPServerStdio

from backend.config import MCP_SERVER_SCRIPT, PROJECT_ROOT

# Tools that only a human may trigger (via the dashboard / backend endpoints).
HUMAN_ONLY_TOOLS = frozenset(
    {"decide_approval_request", "execute_approved_payment", "place_approved_purchase_order"}
)

READ_TOOLS = frozenset(
    {
        "list_tickets",
        "get_ticket",
        "check_inventory_stock",
        "check_vendor_status",
        "get_lease_rent_status",
        "get_pricing_and_margin",
        "get_cash_position",
        "list_approval_requests",
        "list_customer_drafts",
    }
)

# Least-privilege MCP tool allow-list per agent (delegate_task is added separately).
ROLE_TOOLS: dict[str, frozenset[str]] = {
    "boss": READ_TOOLS | {"update_ticket"},
    "inventory": frozenset(
        {"get_ticket", "check_inventory_stock", "check_vendor_status",
         "get_pricing_and_margin", "list_approval_requests"}
    ),
    "accounting": READ_TOOLS
    | {"request_payment_approval", "request_purchase_order_approval", "request_price_override_approval"},
    "facilities": frozenset(
        {"list_tickets", "get_ticket", "get_lease_rent_status", "get_cash_position", "list_approval_requests"}
    ),
    "customer_service": frozenset(
        {"get_ticket", "check_inventory_stock", "check_vendor_status", "get_pricing_and_margin",
         "list_approval_requests", "list_customer_drafts", "save_customer_draft"}
    ),
}

for _role, _tools in ROLE_TOOLS.items():
    assert not (_tools & HUMAN_ONLY_TOOLS), f"{_role} must not get human-only tools"


def build_mcp_server() -> MCPServerStdio:
    """Start mcp_server/server.py over stdio with the same Python interpreter."""
    return MCPServerStdio(
        sys.executable,
        args=[str(MCP_SERVER_SCRIPT)],
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )


def toolset_for(server: MCPServerStdio, role: str):
    allowed = ROLE_TOOLS[role] - HUMAN_ONLY_TOOLS
    return server.filtered(lambda ctx, tool_def: tool_def.name in allowed)
