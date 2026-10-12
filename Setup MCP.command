#!/bin/bash
# Double-click to create the local .venv and install the MCP server dependency.
cd "$(dirname "$0")" || exit 1
echo "== Campus Customs: MCP setup in $(pwd)"

if [ ! -d .venv ]; then
  python3 -m venv .venv || { echo "Failed to create .venv"; read -r -p "Press Enter to close"; exit 1; }
fi
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt -q || { echo "pip install failed"; read -r -p "Press Enter to close"; exit 1; }

# Make sure the working DB exists (copy from the untouched original if missing).
if [ ! -f data/campus_customs_new.db ]; then
  cp data/campus_customs.db data/campus_customs_new.db
  echo "Created data/campus_customs_new.db from the original."
fi

# Project-scoped MCP server list for Claude Code (.mcp.json at project root).
cat > .mcp.json <<'JSON'
{
  "mcpServers": {
    "campus-customs": {
      "type": "stdio",
      "command": ".venv/bin/python",
      "args": ["mcp_server/server.py"],
      "env": {}
    }
  }
}
JSON
echo "Wrote .mcp.json"

echo "== Import check"
.venv/bin/python -c "import sys; sys.path.insert(0,'mcp_server'); import server; print('MCP server imports OK, DB:', server.DB_PATH)"

echo
echo "Done. Now open Claude Code in this folder:  cd \"$(pwd)\" && claude"
echo "Then run /mcp and approve 'campus-customs'."
read -r -p "Press Enter to close"
