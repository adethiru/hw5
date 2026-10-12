#!/bin/bash
# Double-click: one tiny live test that gpt-6-luna can call a tool (about 1 cent).
cd "$(dirname "$0")" || exit 1
echo "== Testing gpt-6-luna tool calling (chat completions, reasoning_effort=none)"
.venv/bin/python -m backend.llm_check
if [ $? -ne 0 ]; then
  echo
  echo "== Chat API failed. Trying the Responses API instead…"
  CC_LLM_API=responses .venv/bin/python -m backend.llm_check
fi
echo
read -n1 -rp "Press any key to close…"
