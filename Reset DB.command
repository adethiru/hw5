#!/bin/bash
# Double-click: copy data/campus_customs.db over data/campus_customs_new.db (clean start).
# The audit trail is kept; a db_reset record with the starting balance is added.
cd "$(dirname "$0")" || exit 1
.venv/bin/python -m backend.reset_db
echo "Now refresh the dashboard in your browser (Cmd+R)."
read -n1 -rp "Press any key to close…"
