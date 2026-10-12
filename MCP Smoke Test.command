#!/bin/bash
# Double-click: Problem 4 evidence -> output/mcp_smoke.json, then checks it against the DB.
#  1st choice: Claude Code (the vibe coder) connected via .mcp.json calls the 3 tools.
#  Fallback:   a real MCP client (Python SDK) connects to the same server over stdio.
cd "$(dirname "$0")" || exit 1
[ -f .mcp.json ] || printf '{\n  "mcpServers": {\n    "campus-customs": {\n      "type": "stdio",\n      "command": ".venv/bin/python",\n      "args": ["mcp_server/server.py"],\n      "env": {}\n    }\n  }\n}\n' > .mcp.json
rm -f output/mcp_smoke.json

PROMPT='Using ONLY the campus-customs MCP server tools, run these three tests, then write the file output/mcp_smoke.json.
Test 1 - prompt: "How many CC-HOOD-NAVY size M hoodies are on hand for ticket 103, which needs 20?" - call check_inventory_stock with sku "CC-HOOD-NAVY", size "M", qty_needed 20.
Test 2 - prompt: "What is Bulldog Print Co (vendor 1) status - lead time, open invoices, will it ship?" - call check_vendor_status with vendor_id 1.
Test 3 - prompt: "What rent is due on lease 1 for ticket 102?" - call get_lease_rent_status with lease_id 1.
Write output/mcp_smoke.json as JSON: {"client": "Claude Code", "mcp_server": "campus-customs", "database": "data/campus_customs_new.db", "tests": [ {"prompt": ..., "tool": ..., "arguments": {...}, "tool_output": <the exact raw JSON object the tool returned, unmodified>} ]}.
Do not invent or edit any values.'

if command -v claude >/dev/null 2>&1; then
  echo "== Trying Claude Code with the campus-customs MCP server (up to ~2 min)…"
  claude -p "$PROMPT" --mcp-config .mcp.json \
    --allowedTools "mcp__campus-customs__check_inventory_stock,mcp__campus-customs__check_vendor_status,mcp__campus-customs__get_lease_rent_status,Write" \
    || echo "Claude Code run did not finish."
else
  echo "== Claude Code not installed."
fi

if [ ! -s output/mcp_smoke.json ]; then
  echo
  echo "== Using the MCP Python client fallback (real MCP protocol over stdio)…"
  .venv/bin/python mcp_server/smoke_test.py || { echo "✖ Fallback failed - paste the text above to Claude."; read -n1; exit 1; }
fi

echo
echo "== Checking output/mcp_smoke.json against the database"
.venv/bin/python mcp_server/verify_smoke.py
echo
read -n1 -rp "Press any key to close…"
