#!/bin/bash
# Double-click: installs everything, resets the DB, and opens the backend + dashboard
# in their own Terminal windows. Then use the board in your browser.
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
say()  { printf "\n\033[1m▶ %s\033[0m\n" "$1"; }
fail() { printf "\n\033[31m✖ %s\033[0m\n" "$1"; read -n1 -rp "Press any key to close…"; exit 1; }

say "Python environment"
[ -d .venv ] || python3 -m venv .venv || fail "python3 not found"
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt || fail "pip install failed (see above). Paste the error to Claude."
.venv/bin/python -c "import mcp, pydantic_ai, fastapi, uvicorn, dotenv; print('✓ Python packages OK')" || fail "Package import failed."

say "API key"
if [ -f .env ] || [ -f ../.env ]; then echo "✓ .env found"; else fail "No .env. Copy .env.example to .env and add PORTKEY_API_KEY."; fi

say "MCP .json for Claude Code"
if [ ! -f .mcp.json ]; then
  printf '{\n  "mcpServers": {\n    "campus-customs": {\n      "type": "stdio",\n      "command": ".venv/bin/python",\n      "args": ["mcp_server/server.py"],\n      "env": {}\n    }\n  }\n}\n' > .mcp.json
fi
echo "✓ .mcp.json"

say "Wiring check (no model calls)"
.venv/bin/python -m backend.check_setup || fail "check_setup failed. Paste the error to Claude."

say "Dashboard packages"
command -v npm >/dev/null || fail "Node.js is not installed. Install the LTS from https://nodejs.org then run this again."
( cd frontend && [ -d node_modules ] || npm install ) || fail "npm install failed."

say "Resetting the working DB (clean start)"
.venv/bin/python -m backend.reset_db || fail "reset failed"
mkdir -p output/screenshots

say "Opening backend and dashboard windows"
osascript -e "tell application \"Terminal\" to do script \"cd '$ROOT/backend' && ../.venv/bin/uvicorn main:app --reload --port 8000\""
sleep 4
osascript -e "tell application \"Terminal\" to do script \"cd '$ROOT/frontend' && npm run dev\""

cat <<'EOF'

✓ Backend:   http://localhost:8000   (window 1)
✓ Dashboard: http://localhost:5173   (window 2 — your browser opens it)

Next, on the board:
  1. Type your name in "Approving as".
  2. 101 → Run agent team → when resolved, approve invoice 501 ($840) FIRST, then the tee PO.
     Screenshot (Cmd+Shift+4) → save as output/screenshots/ticket_101.png
  3. 102 → Run → approve rent ($2,400) → screenshot ticket_102.png
  4. 103 → Run → approve/reject the discount and hoodie PO → screenshot ticket_103.png
  5. Double-click "Build Report.command"
  6. Double-click "Upload hw5 to GitHub.command"
EOF
read -n1 -rp "Press any key to close this window (servers keep running in the other windows)…"
