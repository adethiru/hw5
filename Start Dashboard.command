#!/bin/bash
# Double-click to start the React desk at http://localhost:5173 (start the backend first).
cd "$(dirname "$0")/frontend" || exit 1
if [ ! -d node_modules ]; then
  echo "== Installing dashboard dependencies (first run)…"
  npm install || { echo "npm install failed"; read -r -p "Press Enter to close"; exit 1; }
fi
npm run dev
read -r -p "Dashboard stopped. Press Enter to close"
