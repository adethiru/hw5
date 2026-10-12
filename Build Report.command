#!/bin/bash
# Double-click AFTER the full run (reset -> 101 -> 102 -> 103 + approvals + screenshots).
cd "$(dirname "$0")" || exit 1
mkdir -p output/screenshots
.venv/bin/python -m backend.build_report
read -r -p "Press Enter to close"
