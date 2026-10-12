# Campus Customs — Agent Harness

This is the complete reference for the Campus Customs multi-agent team.

**Contents:**

1. Database tables
2. How the tickets link
3. The first three MCP tools
4. The five agents
5. All 17 MCP tools and their tables
6. Safety rules and token limits
7. Backend API routes
8. Dashboard
9. Full run and report (Problem 9)

- **Original DB (never modified):** `data/campus_customs.db`. Reset by copying it over the working copy.
- **Working DB (MCP server and backend):** `data/campus_customs_new.db`
- **Model:** `gpt-6-luna` only, called through Portkey with `PORTKEY_API_KEY`

---

## 1. Database tables

### `desk`
Fields: `date_today` (TEXT), `notes` (TEXT)

Why it matters: `date_today` (currently **2026-08-31**) is "today" for the shop. Every overdue, due-soon and lead-time calculation uses it, never the real clock.

### `tickets`
Fields: `id` (PK), `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id` (FK → leases), `invoice_id` (FK → invoices), `status`, `notes`, `created_at`

Why it matters: this is the work queue. The Boss reads each open ticket, and its `type` and foreign keys tell the team which other tables and agents are involved.

### `inventory`
Fields: `sku`, `name`, `size`, `qty`, `location` (PK = `sku` + `size`)

Why it matters: Inventory checks stock by SKU and size here and finds shortfalls (requested qty minus on-hand qty).

### `pricing`
Fields: `sku` (PK), `unit_cost`, `list_price`

Why it matters: Accounting uses it to compute margins, decide how big a discount is acceptable, and cost out purchase orders (shortfall × `unit_cost`).

### `vendors`
Fields: `id` (PK), `name`, `specialty`, `lead_days`

Why it matters: Inventory picks a restock vendor by `specialty` and gets the delivery date from `date_today + lead_days`. There is no SKU→vendor link, so matching is done by specialty.

### `invoices`
Fields: `id` (PK), `vendor_id` (FK → vendors), `amount`, `due_date`, `status`, `description`

Why it matters: these are bills the shop owes. An invoice is overdue if `status = 'open'` and `due_date < date_today`. **A vendor with any open invoice will not ship new product**, so this table can block restocks.

### `leases`
Fields: `id` (PK), `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`

Why it matters: Facilities owns this table. It covers rent amount and due date. After rent is paid, `next_due` should move forward one month.

### `cash_accounts`
Fields: `name` (PK), `balance`, `date`

Why it matters: this is the only source of cash (checking = **$3,400.00**). The pay tool must refuse any payment that would make the balance negative. Cash only goes out; there is no revenue in this homework.

### `payments`
Fields: `id` (PK), `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`

Why it matters: this is the audit trail of money out. It starts empty. Every row needs a human in `approved_by`, and `kind`/`ref_id` point to the invoice or lease that was paid.

> Note: there is no `purchase_orders` table. Starting in Problem 5, the MCP server adds two **board tables** to the working DB (`CREATE TABLE IF NOT EXISTS`):
>
> - `approval_requests` holds pending payments, POs and price overrides waiting for the human.
> - `customer_drafts` holds message drafts, which are never sent.
>
> A reset from the original DB starts with an empty board.

---

## 2. How the three open tickets link to other tables

| Ticket | Type | Links | What the data shows | Agents involved |
|---|---|---|---|---|
| **101**: Tauhid Zaman, "Bulldog tee" | `customer_order` | `inventory` (CC-TEE-WHITE, S), `invoice_id` → **501** → vendor 1 | Size S stock = **0**, so the shortfall is 1. The apparel vendor is Bulldog Print Co (5-day lead). Invoice 501 (**$840**, due 2026-08-28, `open`) is **overdue**, so Bulldog won't ship until it's paid. | Boss, Inventory, Accounting, Customer Service |
| **102**: Elm City Properties, "Rent due" | `rent_notice` | `lease_id` → **1** (Chapel Street shop) | Rent is **$2,400**, due **2026-09-02**. That's 2 days out, so it isn't overdue yet. | Boss, Facilities, Accounting |
| **103**: Yale AI Club, "Bulk hoodie discount" | `price_override` | `inventory` + `pricing` (CC-HOOD-NAVY, M) | They want 20 hoodies in size M, but stock = **8**, so the shortfall is 12. Unit cost is $22 and list price is $58 (62% margin at list). Restocking also needs Bulldog Print Co, so it's also blocked by invoice 501. | Boss, Inventory, Accounting, Customer Service |

### Cross-ticket tensions the team must handle

- **Invoice 501 is the bottleneck.** Tickets 101 and 103 both need Bulldog Print Co, so paying 501 (with human approval) unlocks both. The earliest restock arrival is 2026-08-31 + 5 days = **2026-09-05**.
- **Cash is tight.** $3,400 − $840 (invoice 501) − $2,400 (rent) = **$160 left**. A 12-hoodie restock PO at cost (12 × $22 = **$264**) would not fit after both payments, so the team must prioritize and flag this for the human.
- **Payments always need human approval.** Agents only *prepare* payments and POs; a human approves them on the dashboard.
- **No outbound contact.** Customer Service drafts messages for Tauhid Zaman and the Yale AI Club, and the drafts stay on the board.

---

## 3. MCP tools (`mcp_server/server.py`, FastMCP, working DB `data/campus_customs_new.db`)

All three tools are read-only, use `desk.date_today` as "today", and return only database values or simple arithmetic on them.

### Tool 1 — `check_inventory_stock(sku, size=None, qty_needed=None)`

- **Reads:** `inventory` (`sku`, `name`, `size`, `qty`, `location`). It looks up the composite key `sku` + `size`.
- **Unlocks:** **Ticket 103** (Yale AI Club, 20 × CC-HOOD-NAVY size M). It also serves ticket 101.
- **Why it's the right tool:** Ticket 103 can't be priced or promised until the team knows that only **8** size-M hoodies are on hand in Aisle A. Calling it with `qty_needed=20` returns a **shortfall of 12**, which tells Inventory how many units to restock and Accounting how big a purchase order to cost. (For ticket 101, it shows CC-TEE-WHITE size S has **0** on hand, a shortfall of 1, so the order can't be filled from the shelf.)

### Tool 2 — `check_vendor_status(vendor_id=None)`

- **Reads:** `vendors` (`name`, `specialty`, `lead_days`) joined to `invoices` (`id`, `amount`, `due_date`, `status`, `description`) where `status = 'open'`, plus `desk.date_today` to flag overdue invoices.
- **Unlocks:** **Ticket 101** (Tauhid Zaman, 1 × CC-TEE-WHITE size S). The same result also gates the hoodie restock for ticket 103.
- **Why it's the right tool:** Ticket 101 already points at `invoice_id = 501`. This tool shows that 501 belongs to Bulldog Print Co (vendor 1, apparel reprint, 5 lead days), is **$840 and 3 days overdue** (due 2026-08-28), and therefore makes `will_ship_new_product = false`. That tells the Boss the tee can't be reordered until a human approves paying invoice 501, after which the earliest arrival is **2026-09-05**.

### Tool 3 — `get_lease_rent_status(lease_id)`

- **Reads:** `leases` (`space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`), `desk.date_today`, and `cash_accounts` (`name`, `balance`, `date`).
- **Unlocks:** **Ticket 102** (Elm City Properties, "Rent due", `lease_id = 1`).
- **Why it's the right tool:** Ticket 102 is only an email claiming rent is due in 2 days. This tool checks that claim against lease 1: the Chapel Street shop owes **$2,400** due **2026-09-02**, so it's **2 days out and not yet overdue**. It also confirms checking ($3,400) covers it and would leave **$1,000**. Facilities and Accounting can then prepare the rent payment for human approval with real numbers.

---

## 4. The agent team (PydanticAI, `backend/`)

Every agent runs on **`gpt-6-luna`**, configured once in `backend/config.py` and built in `backend/llm.py` through Portkey with `PORTKEY_API_KEY`. No temperature override is set.

**Azure tool-calling note:** Azure's `gpt-6-luna` rejects function tools on `/v1/chat/completions` while reasoning is on. Every agent therefore sets `openai_reasoning_effort="none"` (`backend/llm.py`). The alternative is `CC_LLM_API=responses`, which uses the `/v1/responses` API instead. `python -m backend.llm_check` makes one tiny live tool call to verify the setup.

Every agent reaches the shop **only through the MCP server**. Each one gets a role-filtered view of the same MCP connection (`backend/mcp_client.py`) and a `delegate_task(to_agent, task)` tool, so any agent can hand work to any other (**full connectivity**).

| Agent | File / prompt | Job | MCP tools it may call | Output |
|---|---|---|---|---|
| **Boss** | `agents/boss.py`, `prompts/boss.md` | Reads each ticket, routes it to specialists in dependency order, checks their work and the cash across the board, sets the ticket status, and makes the final call | all read tools + `update_ticket` | `TicketDecision` |
| **Inventory** | `agents/inventory.py`, `prompts/inventory.md` | Stock by SKU + size, shortfall, aisle; picks the restock vendor by specialty; lead time, ship block, earliest arrival | `get_ticket`, `check_inventory_stock`, `check_vendor_status`, `get_pricing_and_margin`, `list_approval_requests` | `SpecialistReport` |
| **Accounting** | `agents/accounting.py`, `prompts/accounting.md` | Cash, invoices and margins. **The only agent that files** payment, PO and price-override requests. Sets the payment priority order | all read tools + `request_payment_approval`, `request_purchase_order_approval`, `request_price_override_approval` | `SpecialistReport` |
| **Facilities** | `agents/facilities.py`, `prompts/facilities.md` | Leases, landlord and rent: checks notices against `leases`, flags mismatches, and passes payment to Accounting | `list_tickets`, `get_ticket`, `get_lease_rent_status`, `get_cash_position`, `list_approval_requests` | `SpecialistReport` |
| **Customer Service** | `agents/customer_service.py`, `prompts/customer_service.md` | Writes honest, warm customer drafts with no internal details. Saves to the board only; never sends | `get_ticket`, `check_inventory_stock`, `check_vendor_status`, `get_pricing_and_margin`, `list_approval_requests`, `list_customer_drafts`, `save_customer_draft` | `SpecialistReport` |

`prompts/team_rules.md` is appended to every agent's prompt. It covers facts coming only from MCP, shop dates, money rules, no outbound contact, delegation and the token budget.

**Agent loop and audit.**

- `CampusCustomsTeam.run_agent_loop` (`backend/team.py`) drives each agent with PydanticAI's `agent.iter()`.
- **Every graph node** (user prompt → model request → model response with tool calls → … → end) is **appended** to `output/audit_trail.json`. Each record includes:
  - `run_id`, `ticket_id`, `agent`, `model`, `depth`
  - the delegation `chain`
  - the step number
  - the tool calls with their args, and the tool returns
  - the model's text, the `model_name` reported by the API
  - cumulative token usage
- Delegations, refused delegations, errors and the final `TicketDecision` are logged too.
- The file is a JSON array that is read, appended to and written back atomically. It is never wiped.

**Running.**

- `python -m backend.check_setup` checks the wiring without calling the model.
- `python -m backend.run_team --ticket 101` runs one ticket.
- `python -m backend.run_team --all` **resets the DB first**, then runs every open ticket one at a time.

---

## 5. All MCP tools (`mcp_server/server.py`) and the tables they use

| # | Tool | Tables read | Tables written | Who can call it |
|---|---|---|---|---|
| 1 | `list_tickets(status)` | `tickets`, `desk` | — | Boss, Accounting, Facilities |
| 2 | `get_ticket(ticket_id)` | `tickets`, `invoices`, `vendors`, `leases`, `inventory`, `pricing`, `approval_requests`, `customer_drafts`, `desk` | — | all agents |
| 3 | `check_inventory_stock(sku, size, qty_needed)` | `inventory` | — | Boss, Inventory, Accounting, Customer Service |
| 4 | `check_vendor_status(vendor_id)` | `vendors`, `invoices`, `desk` | — | Boss, Inventory, Accounting, Customer Service |
| 5 | `get_lease_rent_status(lease_id)` | `leases`, `cash_accounts`, `desk` | — | Boss, Accounting, Facilities |
| 6 | `get_pricing_and_margin(sku, proposed_unit_price, qty)` | `pricing` | — | Boss, Inventory, Accounting, Customer Service |
| 7 | `get_cash_position()` | `cash_accounts`, `invoices`, `vendors`, `leases`, `approval_requests`, `desk` | — | Boss, Accounting, Facilities |
| 8 | `list_approval_requests(status, ticket_id)` | `approval_requests` | — | all agents |
| 9 | `list_customer_drafts(ticket_id)` | `customer_drafts` | — | Boss, Accounting, Customer Service |
| 10 | `request_payment_approval(target_type, target_id, …)` | `invoices`, `vendors`, `leases`, `cash_accounts`, `approval_requests`, `desk` | `approval_requests` (pending) | Accounting |
| 11 | `request_purchase_order_approval(vendor_id, sku, size, qty, …)` | `vendors`, `inventory`, `pricing`, `invoices`, `desk` | `approval_requests` (pending) | Accounting |
| 12 | `request_price_override_approval(ticket_id, sku, qty, proposed_unit_price, …)` | `pricing`, `tickets` | `approval_requests` (pending) | Accounting |
| 13 | `save_customer_draft(ticket_id, recipient, subject, body, …)` | `tickets` | `customer_drafts` (draft) | Customer Service |
| 14 | `update_ticket(ticket_id, status, note, …)` | `tickets`, `desk` | `tickets` (status, appended note) | Boss |
| 15 | `decide_approval_request(request_id, decision, decided_by)` | `approval_requests` | `approval_requests` (approved/rejected) | **Human only** |
| 16 | `execute_approved_payment(request_id)` | `approval_requests`, `cash_accounts`, `invoices`, `leases`, `desk` | `cash_accounts` (debit), `payments` (new row), `invoices.status='paid'` or `leases.next_due` +1 month, `approval_requests` (executed) | **Human only** |
| 17 | `place_approved_purchase_order(request_id)` | `approval_requests`, `invoices`, `vendors`, `cash_accounts`, `desk` | **Prepaid**: `cash_accounts` (debit qty × unit_cost), `payments` (new row, kind `purchase_order`), `approval_requests` (executed). Simulated; no real vendor contacted | **Human only** |

Problem 3 introduced `check_inventory_stock`, `check_vendor_status` and `get_lease_rent_status` (#3–5). Problem 5 added the other 14 (#1–2, #6–17).

---

## 6. Safety

### Guardrails for real customers and real money

Each guardrail is enforced in code, not only in prompts.

- **A human approves all money.** Agents can only file *pending* requests. Approving (`decide_approval_request`) and paying (`execute_approved_payment`) are removed from every agent's toolset. The pay tool also refuses unless the request is `approved` by a human name. Agent names are rejected as approvers.
- **No negative balances.** The pay tool and the PO tool both check the balance inside a DB transaction and refuse if cash is short. Everything is rolled back on any error.
- **Purchase orders are prepaid.** An approved PO debits checking (qty × `unit_cost`) and is written to `payments`, so every dollar out appears in one ledger. Agents include queued POs in their cash math.
- **Amounts come from the DB.** Payment amounts are pulled from `invoices.amount` or `leases.monthly_rent`, and PO cost from `pricing.unit_cost × qty`. Agents cannot type a dollar figure.
- **No duplicate payments.** A second pending or approved request for the same invoice or lease is refused. Paid invoices can't be paid again.
- **Price floor.** Price overrides below `unit_cost` are refused. The policy caps discounts at 15% off list and requires at least 40% margin.
- **Vendor rule enforced.** POs can't be placed while the vendor has an open invoice. In practice, invoice 501 must be paid before any Bulldog Print Co order.
- **Nothing leaves the building.** Customer messages are drafts only, and the recipient must be the ticket's requester. There are no email, phone or vendor-contact tools.
- **Least privilege.** Each agent sees only the MCP tools its role needs.
- **Facts only from tools.** Prompts forbid invented data. Outputs must list each fact with its source tool.
- **Full audit trail.** Every loop step, tool call, delegation and decision is appended to `output/audit_trail.json`, with the model name and token usage.
- **Safe reset.** `campus_customs.db` is never written to. `--all` resets the working copy before a full run.
- **Secrets stay out of code.** `PORTKEY_API_KEY` is read from `.env`, which is git-ignored. The model name lives in one constant, with a runtime check that it equals `gpt-6-luna`.

**What a real business would add:**

- Two-person approval above a dollar threshold
- Daily payment caps
- A vendor bank-detail change check
- PII redaction in logs
- Rate limits per customer
- Human review of drafts before sending
- Monitoring and alerts on refused or failed actions

### Limits that keep token use in check

- **One shared budget per ticket** across the whole delegation tree, via PydanticAI `UsageLimits`:
  - 40 model requests
  - 60 tool calls
  - 200k tokens

  These can be overridden with `CC_REQUEST_LIMIT`, `CC_TOOL_CALLS_LIMIT` and `CC_TOKEN_LIMIT`. Going over the budget stops the ticket cleanly and logs it.
- **Delegation caps:**
  - maximum depth 3
  - maximum 8 hand-offs per ticket
  - no self-delegation
  - no delegating back up the current chain, which prevents ping-pong loops
- **Tool retries** are capped at 2 per agent.
- **Tickets run one at a time** rather than in parallel. This avoids cash races and token spikes.
- **Compact tool results.** Tool outputs return only the needed fields. Audit payloads are clipped at 4,000 characters.
- **Prompt rules** tell agents to call each tool once per question, reuse teammates' facts, keep text short and stop when they hit a budget refusal.
- `check_setup` lets you verify the wiring with **zero model calls**.

---

## 7. Backend routes (`backend/main.py`, FastAPI)

**Start:** from `backend/`, run `uvicorn main:app --reload --port 8000` (or double-click `Start Backend.command`). The backend is then at `http://localhost:8000`, with interactive docs at `/docs`.

Every route reads and writes the shop through the **same MCP server** the agents use, over one stdio connection held for the app's lifetime. Ticket runs happen one at a time.

- `GET /api/health`: liveness, the model name (`gpt-6-luna`), and whether a run is in progress.
- `GET /api/tickets`: all tickets with their DB `status` and an open/resolved flag (`state`, `is_resolved`).
- `GET /api/tickets/{id}`: one ticket with its linked invoice, lease, inventory and pricing, plus its approvals and drafts.
- `POST /api/tickets/{id}/run`: runs the agent team (Boss first) on that ticket in the background and returns a `run_id`. Add `?wait=true` to block until it's done. Returns 409 if another run is active.
- `GET /api/runs/{run_id}` (and `GET /api/runs`): run status (`queued`, `running`, `done`, `error` or `stopped_usage_limit`) and the Boss's `TicketDecision`.
- `GET /api/events?after=&limit=&ticket_id=&run_id=&agent=`: recent agent events from `audit_trail.json`, meaning what each agent said, the tools it called with their args, tool results, delegations and final outputs. `next_after` supports incremental refresh.
- `GET /api/approvals?status=&ticket_id=`: the approval queue (payments, purchase orders and price overrides prepared by Accounting).
- `GET /api/drafts?ticket_id=`: customer message drafts. They're never sent.
- `POST /api/approvals/{id}/approve` with body `{"approved_by": "<human>", "note": ""}`: **the only path that moves money.**
  - A payment is approved, then paid. That debits `cash_accounts`, inserts into `payments`, and marks the invoice paid or moves `leases.next_due` forward.
  - A purchase order is approved, then placed. This is refused while the vendor has an open invoice.
  - A price override is approved only.
  - Returns 409 if cash would go negative. Agent names are rejected as approvers.
- `POST /api/approvals/{id}/reject` with body `{"approved_by": "<human>"}`: rejects a pending request. No changes are made.
- `GET /api/cash`: the current checking balance from `cash_accounts`, plus the open invoice total, queued payments and cash after them.
- `GET /api/payments`: approval requests that have been executed (an audit view of the money that went out).
- `POST /api/reset`: copies `data/campus_customs.db` over `data/campus_customs_new.db` for a fresh run. The audit trail is kept. Returns 409 during a run.

**Ticket status:** when a run finishes and the Boss didn't report `blocked`, the ticket is `resolved`. Usually the Boss sets this through `update_ticket`; otherwise the backend sets it with `updated_by="system"`. Pending human approvals stay listed on the ticket and in the Approvals panel.

---

## 8. Dashboard (`frontend/`, React + Vite + TypeScript)

- **Start:** `npm install` (first time), then `npm run dev` from `frontend/`. It opens `http://localhost:5173`.
- It calls the backend at `http://localhost:8000`, which allows that origin via CORS.
- See `output/design.md` for the layout, agent identities, resolved and cash cues, and the reasoning behind them.

---

## 9. Full run and report (Problem 9)

**Procedure.**

1. Reset the working DB with the dashboard's **Reset DB** button (or `python -m backend.reset_db`). This appends a `db_reset` record with the starting checking balance, **$3,400.00**.
2. Run tickets **101 → 102 → 103** one at a time from the dashboard.
3. After each run, a human reviews and approves or rejects in the Approvals panel. Only `POST /api/approvals/{id}/approve` moves cash.
4. Take a screenshot of the board for each resolved ticket and save it as `output/screenshots/ticket_<id>.png`.
5. Run `python -m backend.build_report`. It makes **no model calls** and builds the report from real evidence only:
   - **Inputs:** `output/audit_trail.json` (records after the last `db_reset`), the working DB (`tickets`, `approval_requests`, `customer_drafts`, `payments`, `cash_accounts`), and the original DB (for the starting balance).
   - **Outputs:** the Actual sections and Cash tab of `output/desk_tickets.html`, plus `output/resolved_tickets.json` and `output/resolved_board.html` (with the screenshots embedded).

**Cash rule.** Ending checking = starting checking − Σ `payments.amount`. The script stops with an error if this doesn't equal `cash_accounts.balance`, if the balance is negative, or if the audit trail shows any model other than `gpt-6-luna`.

