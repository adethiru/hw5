"""Central configuration for the Campus Customs backend.

MODEL_NAME is defined ONCE here. Every agent uses it - no other model may be
referenced anywhere in this project.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# .env lives in the project root (or the parent workspace folder). Never commit it.
for candidate in (PROJECT_ROOT / ".env", PROJECT_ROOT.parent / ".env"):
    if candidate.exists():
        load_dotenv(dotenv_path=candidate)
        break

# --- Model (the ONLY model allowed in this homework) -----------------------
MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
API_KEY_ENV = "PORTKEY_API_KEY"

# --- Paths -----------------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data"
ORIGINAL_DB = DATA_DIR / "campus_customs.db"      # never modified
WORKING_DB = DATA_DIR / "campus_customs_new.db"   # MCP server + backend use this
MCP_SERVER_SCRIPT = PROJECT_ROOT / "mcp_server" / "server.py"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
OUTPUT_DIR = PROJECT_ROOT / "output"
AUDIT_TRAIL = OUTPUT_DIR / "audit_trail.json"

# --- Token / loop guardrails -----------------------------------------------
# Shared across one ticket's whole delegation tree (usage is passed down).
REQUEST_LIMIT_PER_TICKET = int(os.environ.get("CC_REQUEST_LIMIT", 40))
TOOL_CALLS_LIMIT_PER_TICKET = int(os.environ.get("CC_TOOL_CALLS_LIMIT", 60))
TOTAL_TOKENS_LIMIT_PER_TICKET = int(os.environ.get("CC_TOKEN_LIMIT", 200_000))
MAX_DELEGATION_DEPTH = 3          # boss -> A -> B -> C at most
MAX_DELEGATIONS_PER_TICKET = 8    # total hand-offs in one ticket
AUDIT_TEXT_LIMIT = 4000           # chars kept per text/tool payload in the audit log


def get_api_key() -> str:
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise RuntimeError(f"{API_KEY_ENV} is not set. Put it in .env (never in code).")
    return key
