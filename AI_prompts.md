# AI Prompts — Homework 5: Campus Customs Multi-Agent Operations

This is a log of the prompts I gave the AI assistant while working on this assignment. Each problem has its own section with the problem number and title, at least one prompt I typed, and any follow-up prompts I needed.

---

## Problem 1 — Vibe coder prompts

**Context / setup prompt:**

> OK - so here is the scenario. Campus Customs Multi-Agent Operations is the agentic team that runs the shop. Open tickets land on a board - customer orders, rent, unpaid bills, discount requests, whatever the shop must handle. We will build three pieces that talk to each other - 1) an MCP server, 2) FastAPI backend with a multi-agent team, 3) a React dashboard so a human can watch the agents at work and approve requests. The agent team has full connectivity - any agent may delegate tasks to any other agent for help. We will build the following agents - 1) boss - reads each ticket, decides who should work on it, and makes final calls, 2) inventory- checks stock by SKU and size, spots shortfalls, and figures out which vendor can restock, 3) accounting- watches cash and invoices, checks margins, and prepares payments or purchase orders for human approval, 4) facilities- handles the shop space side (leases, rent etc.), 5) customer service- drafts messages for customers. I have downloaded and saved the data so you have data/campus_customs.db - this is the original shop database. [...] Make a copy of the database file called data/campus_customs_new.db and point MCP server and backend at that working copy. Keep campus_customs.db untouched so you can reset when you want to restart resolving tickets. [...] Human approval is required for any payments. [...] If there is not enough cash, the pay tool must refuse - no negative balances. [...] Use PORTKEY_API_KEY for AI calls and for this homework, use only gpt 6 luna. [...] Final submission will be a public GitHub repo. OK so onto Problem 1.

**Prompt:**

> OK for problem 1. Create AI_prompts.md at the start of the assignment and keep it updated as we work. Put one section for each problem and each section must include: the problem number and title, at least one prompt I typed and one follow-up prompt if I needed it.

**Follow-up prompts:**

> is gpt 6 luna different from 5.6 luna

> I can ONLY use gpt-6-luna model

> Yes exactly for this homework we use gpt-6-luna ONLY

**Result:** Created `AI_prompts.md`. Copied the database to `data/campus_customs.db` (the untouched original) and `data/campus_customs_new.db` (the working copy). Set the model for this homework to `gpt-6-luna` only.

---

## Problem 2 — Study the Campus Customs database

**Prompt:**

> Problem 1: Vibe coder prompts. OK now onto Problem 2: Study the Campus Customs database. Open data/campus_customs.db and look through every table and its fields. Copy the original file to data/campus_customs_new.db - later problems update this working copy. Study the three open tickets so you can see how they link to other tables. Start output/harness.md - for each table, list the fields and one short line on why that table matters for the agents. We will keep growing this harness file in later problems.

**Follow-up prompts:** None needed.

**Result:** Went through all 9 tables. Re-copied the original to `data/campus_customs_new.db` and confirmed with a checksum that the two files are identical. Created `output/harness.md` with each table's fields and why it matters to the agents, plus how tickets 101–103 link to other tables and the conflicts between them (overdue invoice 501 blocks Bulldog Print Co; not enough cash for both bills plus a restock).

---

## Problem 3 — Build the MCP server

**Prompt:**

> Problem 3: Build the MCP server. OK write an MCP server in mcp_server/ using FastMCP. It will talk to data/campus_customs_new.db. You DO NOT need to connect or run it in this problem. Every agent in this homework uses the tools in this MCP server. We will add more tools to it later - for now, write three tools you know you will need for the tickets in the database. Keep the names very clear. DO NOT invent any data and use only information in the database. In output/harness.md, list each of the 3 MCP tools. For every tool include: which table it reads, which ticket it helps unlock (101,102 or 103) and include one sentence on why that tool is the right one for that ticket. Do not make it vague lines like "reads inventory" - must be more detailed and tied to the ticket. Also add a short mcp_server/README.md file that explains what the MCP server is for, which database file it uses and the 3 tools it has.

**Follow-up prompts:** None needed.

**Result:** Wrote `mcp_server/server.py` (FastMCP) with three read-only tools: `check_inventory_stock` (helps ticket 103, and 101), `check_vendor_status` (ticket 101, and the 103 restock), and `get_lease_rent_status` (ticket 102). Added `mcp_server/README.md` and `mcp_server/requirements.txt`, plus a ticket-specific tool section in `output/harness.md`.

---

## Problem 4 — Add the MCP server to the vibe coder and test each tool

**Prompt:**

> OK onto Problem 4: Add the MCP server to vibe coder and test each tool. In Claude Code, add your MCP server to this project so the vibe coder can call the tools. Save the connection JSON text in .mcp.json at the project root (or however your vibe coder saves local MCP server lists). With the vibe coder connected, test each of the 3 MCP tools. Save the evidence in output/mcp_smoke.json For every tool include: the prompt asked the vibe coder, the tool name, the tool output (must match values in data/campus_customs_new.db)

**Follow-up prompts (in Claude Code, with the `campus-customs` MCP server connected):**

> Use the campus-customs MCP tool check_inventory_stock to check how many CC-HOOD-NAVY size M hoodies are on hand for ticket 103, which needs 20.

> Use the campus-customs MCP tool check_vendor_status for vendor 1 to see whether Bulldog Print Co will ship the size S tee for ticket 101.

> Use the campus-customs MCP tool get_lease_rent_status for lease 1 to check the rent due for ticket 102.

> Write output/mcp_smoke.json with the three tests above: for each, the prompt, the tool name and the exact raw tool output. Then run .venv/bin/python mcp_server/verify_smoke.py.

**Result:** `Setup MCP.command` creates `.venv`, installs `mcp`, and writes `.mcp.json` (stdio server `campus-customs` → `.venv/bin/python mcp_server/server.py`). Claude Code called each tool and saved the evidence to `output/mcp_smoke.json`. `mcp_server/verify_smoke.py` checks those values against `data/campus_customs_new.db`.

---

## Problem 5 — Build the agent team and grow the MCP tools

**Prompt:**

> OK onto Problem 5: Build the agent team and grow the MCP tools. Build the agentic team for Campus Customs using PydanticAI: Boss, Inventory, Accounting, Facilities and Customer Service. Include prompts, models, and agent loops so they can delegate work to each other with full connectivity. Put the agent prompts in backend/prompts/ - one file per agent. Put data types in backend/models.py and the agent files under backend/ (layout can vary provided the five roles are clear). Use only gtp-6-luna for every agent. Will need to ensure detailed prompts that cover all aspects of an agent's work and scope - very important. Add any tools agent needs to the MCP server so they can work on the open tickets. Shop facts come from the MCP server over data/campus_customs_new.db - do not invent a second shop-tools layer that bypasses MCP. Wire the agents so they append to output/audit_trail.json as they run: for each agent-loop step, record enough to audit later. Append to this file - do not wipe it each run. In output/harness.md list each agent and each MCP tool (including the ones added in this problem) along with which table the tool uses. Also add a short safety section: the guardrails a real business would want when agents touch real customers and real money plus limits that keep token use in check. Update mcp_server/README.md so the tool list matches what we have now.

**Follow-up prompts:** None needed. ("gtp-6-luna" was read as `gpt-6-luna`.)

**Result:**

- Grew the MCP server from 3 to 17 tools: reads, board-only agent writes, and human-only approve, pay and PO tools.
- Built the PydanticAI team in `backend/`: `config.py` (single model constant `gpt-6-luna`), `llm.py`, `models.py`, `mcp_client.py` (role-filtered MCP toolsets), `agents/` (five role specs), `team.py` (audited agent loop and `delegate_task` for full connectivity, with loop and token guardrails), `audit.py` (append-only `output/audit_trail.json`), `run_team.py` and `reset_db.py`.
- Wrote a detailed prompt per agent in `backend/prompts/`, plus a shared `team_rules.md`.
- Updated `output/harness.md` (agents, all tools and tables, safety) and `mcp_server/README.md`.

---

## Problem 6 — Plan the three tickets

**Prompt:**

> OK onto Problem 6: Plan the three tickets. Before you wire the backend, write down what is expected for the team to do on each open ticket. Build output/desk_tickets.html - a page can double click with one tab per ticket (101,102 and 103). Also add empty Cash and Reflection tabs for later problems (leave them blank for now). On each ticket tab, fill an Expected section only (leave room for an Actual section to fill after we run the agents). For each ticket's Expected sectionm write: who the boss should call first and why, all the agent delegations expected - not "boss calls everyone" and which MCP tools you expect that run to use. Plans that send every specialist on every ticket will score low points. We will compare this plan to what actually happens when agents resolve the three tickets.

**Follow-up prompts:** None needed.

**Result:** Built `output/desk_tickets.html`, a self-contained page that opens by double-click, with tabs for 101, 102, 103, Cash and Reflection (the last two blank). Each ticket tab has an Expected plan and an empty Actual box:

- **101:** Boss → Inventory first, then Accounting, then Customer Service (3 delegations; Facilities not used).
- **102:** Boss → Facilities first, then Accounting (2 delegations; Inventory and Customer Service not used).
- **103:** Boss → Inventory first, then Accounting, then Customer Service (3 delegations; Facilities not used; no duplicate request for invoice 501).

---

## Problem 7 — Backend routes

**Prompt:**

> Now onto Problem 7: Backend routes. React frontend dashboard (the next problem) needs a backend it can call. In backend/main.py use FastAPI and add routes that do the following: return the three tickets and whether each is open or resolved, take a ticket id and run the agent team on that ticket, return recent agent events - what each agent said and which tools they used - so the board can refresh, approve a payment or purchase after a human clicks approve (agents only prepare the pay: the route is what actually changes cash), return the current checking balance from cash_accounts, reset the database to the original values when you want to try a fresh run. From the backend/ folder start the server with: uvicorn main:app --reload --port 8000 this turns on backend at http://localhost:8000 so the frontend dashboard can call those routes. In output/harness.md list each route in one line (what URL / what it does).

**Follow-up prompts:** None needed.

**Result:**

- Wrote `backend/main.py` (FastAPI). Routes cover tickets, running a ticket in the background, run status, agent events from the audit trail, approvals and drafts, human approve/reject (the only route that moves cash), checking balance and reset.
- All routes go through the MCP server. It runs from `backend/` with `uvicorn main:app --reload --port 8000`.
- Added `fastapi` and `uvicorn` to `requirements.txt`, created `Start Backend.command`, and listed the routes in `output/harness.md`.

---

## Problem 8 — Agent dashboard

**Prompt:**

> Ok onto Problem 8: Agent dashboard. Build the frontend dashboard in frontend/ with React + Vite + TypeScript. The page should call the routes built in Problem 7. At minimum the board should do following - list all three tickets, let you pick one ticket and start the agent team on it, show each agent and what they are saying / doing while the ticket runs, mark a ticket resolved when the run finishes, show a short summary of what each agent did on that ticket, let a human approve a pay or purchase when asked, show the checking balance (it should drop after an approved pay). Be creative and make the dashboard look high quality and the layout should feel high quality so take time to make it good.

**Follow-up prompt:**

> Tell the front end to talk to backend at http://localhost:8000. On the backend, allow the Vite page origin (usually http://localhost:5173) so the browser is allowed to call those routes. Start the board with: npm run dev this should open React desk in browser so can pick up the tickets and watch agents. Write output/design.md with what is chosen for dashboard look (layout, how agents read differently, how resolved tickets and cash show up) and why - be as detailed as possible. Make sure it feels special and something humans would enjoy using.

**Result:**

- Built `frontend/` (React + Vite + TypeScript, no UI kit).
- **Layout:**
  - a sticky top bar with an animated checking balance that flashes when it drops
  - a ticket board with a progress bar
  - a ticket stage with a five-agent roster (thinking / waiting / done / not needed, plus a speech bubble), a hand-offs strip, a live threaded feed of tool calls, results, hand-offs and reports, and a Run summary tab (Boss decision, stats, per-agent cards)
  - an approvals panel with cash-impact previews
  - a cash ledger with a sparkline
  - letter-style customer drafts
- **Connection:** the page calls `http://localhost:8000` directly, and backend CORS allows `http://localhost:5173`. `npm run dev` opens the browser.
- **Resolved tickets:** the Boss now marks tickets `resolved` when the team's work is done, with a backend fallback after a finished run. Pending approvals stay flagged.
- Wrote `output/design.md` and added `Start Dashboard.command`.

---

## Problem 9 — Resolve the tickets

**Prompt:**

> Ok onto Problem 9: Resolve the tickets. Before testing the agents on a full run over the three tickets, reset the working database data/campus_customs_new.db again so you start clean. Note the starting checking balance. Then run all three tickets on the board (101,102,103) until each is resolved. Open output/desk_tickets.html from Problem 6. On each ticket tab, fill the Actual section from this run - which agents worked, what they delegated and which tools they used. Keep Expected section so you can compare the two. On the Cash tab of the same output/desk_tickets.html, itemize the money: starting checking balance (after the reset), for each ticket: how cash changed when that ticket resolved and why (which pay / purchase, dollar amount), ending checking balance - it must match cash_accounts in the working database. Wrong cash math will lose points even if the board shows every ticket resolved. Please note this and be careful. Also save output/resolved_tickets.json - for each ticket: id, final status, short outcome, what each agent contributed and any human approvals. output/resolved_board.html - a page you can double click with a screenshot of your React board for each resolved ticket (101,102 and 103). Append real runs to output/audit_trail.json. Finish output/harness.md so it covers tables, MCP tools, the five agents, API routes, the dashboard and safety rules.

**Follow-up prompts:** (add any you used during the run here)

**Result:**

- Made approved purchase orders **prepaid**, so a "purchase" changes cash like a payment. The PO tool refuses when cash is short.
- `reset_db` now logs the starting balance to the audit trail.
- Added `backend/build_report.py`, which fills the Actual sections and Cash tab, `resolved_tickets.json` and `resolved_board.html` from the real audit trail and database. It refuses to write cash figures that don't reconcile with `cash_accounts`.
- Finished `output/harness.md`.
- The run itself (reset → 101 → 102 → 103 with human approvals) is done on the dashboard.

---


## Problem 10 — Reflection

**Prompt:**

> Ok onto Problem 10: Reflection. Open output/desk_tickets.html and fill in Reflection tab. Answer in a detailed and thorough way the following evaluate performance of the agents on each ticket and why, for each ticket how did Actual compare to Expected plan wrote earlier, what would have been simpler as one agent with tools and why, describe three new problems Campus customs might face that this agent team could solve with the tools built, describe three new problems Campus customs might face that this agent team could not solve with the tools built, and explain the tools and agents needed to solve them. Be detailed and comprehensive.

**Follow-up prompt:**

> Link and tie every answer to this app and the three tickets ran - use the ticket tabs and Cash tab on the same page as evidence.

**Result:**

- Filled the Reflection tab of `output/desk_tickets.html`. In-page links jump to the 101, 102, 103 and Cash tabs.
- Written sections: what good performance looks like per ticket; one agent vs. the team (102 should be one agent, 101 is a fixed pipeline, 103 and shared cash justify Accounting); three problems the team can solve with today's tools (mug order via Elm City Gifts, unaffordable next-month rent, the AI Club's partial order); three it can't (revenue and refunds, real procurement and receiving, time and forecasting), with the tables, MCP tools and agents each would need.
- `backend/build_report.py` fills the run-dependent parts from the real audit trail and DB: a per-ticket checklist and score, Actual-vs-Expected findings, and a cost-of-the-team table. The same evaluation goes into `resolved_tickets.json`.

---

## Problem 11 — Submit to GitHub

**Prompt:**

> For Problem 11: Submit to Github. I need to push your code to a public Github repository so graders can clone it. I will need to submit the repo URL and also put it in output/github_url.txt Do not push the real .env to the GitHub repo. Do include both database files under data/ (original and working copy) so graders can run app easily. Expected file layout shared as picture. README should explain; copy original DB to the working copy when you need a clean run, start MCP server, start FastAPI backend, start the React board, reset the DB before a full three-ticket run.

**Follow-up prompts:** None needed.

**Result:**

- Wrote the root `README.md`: setup; copying the original DB to the working copy for a clean run; starting the MCP server, the FastAPI backend and the React board; resetting the DB before the full three-ticket run; the routes; and the report step.
- Added `.env.example` and tightened `.gitignore`. `.env`, `.venv`, `node_modules` and caches are excluded; both DBs in `data/` are included.
- Added `Upload hw5 to GitHub.command`. It:
  - builds a clean copy matching the expected layout
  - refuses to upload if `.env` or the real API key is present
  - creates a public repo (default `adethiru/hw5`) if needed and uploads through the GitHub API
  - writes `output/github_url.txt`

---

## Debugging during the run (Problems 9–11)

**Prompts:**

> Ok can you fix missing items

> getting ticket errors

**Result:**

- **Missing items:** added `Run Everything.command` (install, wiring check, reset, open backend and dashboard windows). The missing outputs are produced by the real run.
- **Ticket errors:** the audit trail showed every run failing with an Azure 400 error: "Function tools with reasoning_effort are not supported for gpt-6-luna-global in /v1/chat/completions… set reasoning_effort to 'none'". The fix:
  - every agent now sets `openai_reasoning_effort="none"`
  - `CC_LLM_API=responses` switches to the Responses API as an alternative
  - `python -m backend.llm_check` runs a one-call live tool test


> it says missing output/mcp_smoke.json

> Can you fix

**Result:** `MCP Smoke Test.command` tries Claude Code first, through `claude -p` with `--mcp-config .mcp.json` and only the three tools allowed. If Claude Code isn't available, it falls back to `mcp_server/smoke_test.py`, a real MCP Python SDK stdio client. Either way it writes `output/mcp_smoke.json`, records which client produced it, and checks the values against the DB with `verify_smoke.py`.
