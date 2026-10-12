# Campus Customs — Multi-Agent Operations (Homework 5)

Five AI agents run the ticket board of **Campus Customs**, a small Yale apparel shop. A human watches them work on a React dashboard and approves anything that spends money.

| Piece | Where | What it does |
|---|---|---|
| **MCP server** | `mcp_server/server.py` (FastMCP) | The only way to read or change shop data in `data/campus_customs_new.db`. It has 17 tools; three of them (approve, pay, place PO) are human-only. |
| **Agent team + API** | `backend/` (PydanticAI + FastAPI) | Boss, Inventory, Accounting, Facilities and Customer Service. Any agent can delegate to any other. Every step is appended to `output/audit_trail.json`. |
| **Dashboard** | `frontend/` (React + Vite + TypeScript) | Pick a ticket, watch the agents live, approve or reject requests, and see the checking balance drop. |

**Model:** every agent uses **`gpt-6-luna`** through Portkey (`PORTKEY_API_KEY`). The model name is defined once, in `backend/config.py`.

---

## Shop rules (enforced in the MCP tools, not just in prompts)

- "Today" is `desk.date_today` (2026-08-31), not the computer clock.
- Vendor lead times come from `vendors.lead_days`.
- A vendor with an open, unpaid invoice won't ship new product.
- **Every payment or purchase needs human approval.** Agents can only file *requests*. Only `POST /api/approvals/{id}/approve` moves money, and it updates `cash_accounts`, `payments`, and `invoices` or `leases`.
- **No negative balances.** The pay and PO tools refuse if checking can't cover the amount.
- Cash only goes out; no revenue is modeled. Purchase orders are prepaid.
- No email is sent and no vendor is contacted. Customer messages stay on the board as drafts.

---

## Project layout

```
hw5/
├── AI_prompts.md            prompts used with the AI coding assistant, per problem
├── requirements.txt         Python deps (mcp<2, pydantic-ai, fastapi, uvicorn, dotenv)
├── .env.example             copy to .env and add your PORTKEY_API_KEY
├── .gitignore               keeps .env, .venv, node_modules out of git
├── .mcp.json                lets Claude Code connect to the MCP server
├── README.md
├── data/
│   ├── campus_customs.db       ORIGINAL, never modified (the reset source)
│   └── campus_customs_new.db   WORKING COPY used by the MCP server + backend
├── mcp_server/  server.py, README.md
├── backend/     main.py (FastAPI), models.py, team.py, agents/, prompts/ (one .md per agent),
│                config.py, llm.py, mcp_client.py, audit.py, reset_db.py, run_team.py, build_report.py
├── frontend/    React + Vite + TypeScript dashboard
└── output/      harness.md, mcp_smoke.json, desk_tickets.html, design.md,
                 resolved_tickets.json, resolved_board.html, audit_trail.json, github_url.txt
```

---

## Run it

You need Python 3.10+, Node 18+, and a Portkey key.

### 0. One-time setup

```bash
cp .env.example .env              # then edit .env and set PORTKEY_API_KEY=...
python3 -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 1. Clean start: copy the original DB over the working copy

The working copy `data/campus_customs_new.db` contains the state of the last run. To start fresh:

```bash
cp data/campus_customs.db data/campus_customs_new.db
# or, which also logs the starting balance to the audit trail:
python -m backend.reset_db
```

`data/campus_customs.db` is never written to, so you can always reset from it.

### 2. Start the MCP server

The backend starts the MCP server itself (over stdio) when it boots, so you don't need a separate terminal for normal use.

- **Run it on its own** (for example, to inspect it):

  ```bash
  python mcp_server/server.py
  ```

- **Use the tools from Claude Code:** open this folder in Claude Code. `.mcp.json` registers the `campus-customs` server (`.venv/bin/python mcp_server/server.py`). Run `/mcp` to approve it.

### 3. Start the FastAPI backend (terminal 1)

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The API is at <http://localhost:8000> (interactive docs at `/docs`). CORS allows the Vite page at `http://localhost:5173`.

### 4. Start the React board (terminal 2)

```bash
cd frontend
npm install        # first time only
npm run dev        # opens http://localhost:5173
```

### 5. Full three-ticket run

1. **Reset the DB first:** click **Reset DB** on the board, or run `python -m backend.reset_db`. Checking should show **$3,400.00**.
2. Type your name in **Approving as** (Approvals panel).
3. Select **101**, then **Run agent team**. Watch the live feed. When it resolves, approve the requests you agree with. The invoice 501 payment must be approved before the Bulldog purchase order can be placed.
4. Repeat for **102**, then **103**. Ticket 103's hoodie PO may be refused if cash is short; that's the no-negative-balance rule working.
5. Save a screenshot of the board after each ticket as `output/screenshots/ticket_<id>.png`.
6. Build the report (no model calls):

   ```bash
   python -m backend.build_report
   ```

   This fills the Actual, Cash and Reflection evidence in `output/desk_tickets.html` and writes `output/resolved_tickets.json` and `output/resolved_board.html`. It **stops with an error** if start balance − payments ≠ `cash_accounts.balance`.

**Without the board:** `python -m backend.run_team --all` resets the DB and runs all open tickets. Approvals still happen on the board or through the API.

---

## API routes (backend/main.py)

| Route | Purpose |
|---|---|
| `GET /api/tickets` | All tickets with an open/resolved flag |
| `POST /api/tickets/{id}/run` | Run the agent team on a ticket (background; returns `run_id`) |
| `GET /api/runs/{run_id}` | Run status and the Boss's decision |
| `GET /api/events?after=N` | Recent agent events: who said what and which tools they used |
| `GET /api/approvals`, `GET /api/drafts` | Approval queue and customer drafts |
| `POST /api/approvals/{id}/approve` | **Human approval.** Pays or places the order and changes cash. Refuses negative balances. |
| `POST /api/approvals/{id}/reject` | Reject a request |
| `GET /api/cash` | Current checking balance from `cash_accounts` |
| `POST /api/reset` | Copy the original DB over the working copy |

The full reference (tables, all MCP tools, agents, routes, dashboard, safety and token limits) is in **`output/harness.md`**.

---

## Helpful checks

```bash
python -m backend.check_setup          # lists MCP tools + each agent's allowed tools, zero model calls
python mcp_server/verify_smoke.py      # checks output/mcp_smoke.json against the DB
```

macOS shortcuts (double-click): `Setup MCP.command`, `Start Backend.command`, `Start Dashboard.command`, `Build Report.command`.
