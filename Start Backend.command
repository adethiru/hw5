#!/bin/bash
# Double-click to start the Campus Customs backend at http://localhost:8000
cd "$(dirname "$0")/backend" || exit 1
echo "== Campus Customs backend (gpt-6-luna) on http://localhost:8000  - docs at /docs"
../.venv/bin/uvicorn main:app --reload --port 8000
read -r -p "Server stopped. Press Enter to close"
