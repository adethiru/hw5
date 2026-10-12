# Campus Customs MCP Server

**What it's for:** This is the one shared toolbox for the Campus Customs agent team (Boss, Inventory, Accounting, Facilities, Customer Service). Agents get shop facts and take shop actions **only** through these tools, so every agent sees the same data and the shop rules are enforced in one place. It's built with **FastMCP** (`mcp` Python SDK).

**Database:** `data/campus_customs_new.db`, the *working copy*. The original `data/campus_customs.db` is never touched. Copy it over the working copy to reset (`python -m backend.reset_db`).

The server adds two board tables to the working DB if they're missing:

- `approval_requests` holds pending payments, POs and price overrides.
- `customer_drafts` holds message drafts, which are never sent.

**Rules enforced in the tools:**

- "Today" is `desk.date_today`, never the computer clock.
- A vendor with an open invoice won't ship.
- Payments need a human-approved request.
- The pay tool refuses if the balance would go negative.
- Amounts come from the DB.
- Customer messages are drafts only.
- No data is invented.

## Tools (17)

**Read**

| Tool | Tables | Purpose |
|---|---|---|
| `list_tickets(status="open")` | tickets, desk | Tickets on the board |
| `get_ticket(ticket_id)` | tickets + linked invoices/vendors/leases/inventory/pricing, board tables | One ticket with everything it links to |
| `check_inventory_stock(sku, size, qty_needed)` | inventory | On-hand stock by SKU and size, plus shortfall |
| `check_vendor_status(vendor_id=None)` | vendors, invoices, desk | Lead days, open/overdue invoices, will-ship flag, earliest arrival |
| `get_lease_rent_status(lease_id)` | leases, cash_accounts, desk | Rent, due date, days until due, cash after rent |
| `get_pricing_and_margin(sku, proposed_unit_price, qty)` | pricing | Cost, list price, margin, discount percentage, totals |
| `get_cash_position()` | cash_accounts, invoices, leases, approval_requests, desk | Balances, bills owed, queued payments |
| `list_approval_requests(status, ticket_id)` | approval_requests | Board approval queue |
| `list_customer_drafts(ticket_id)` | customer_drafts | Board drafts |

**Agent write (board only, no money moves)**

| Tool | Writes | Purpose |
|---|---|---|
| `request_payment_approval(target_type, target_id, ticket_id, reason, requested_by)` | approval_requests | Pending payment for an invoice or rent; amount taken from the DB; no duplicates |
| `request_purchase_order_approval(vendor_id, sku, size, qty, ticket_id, reason, requested_by)` | approval_requests | Pending restock PO; cost = qty × unit_cost; flags a vendor block |
| `request_price_override_approval(ticket_id, sku, qty, proposed_unit_price, reason, requested_by)` | approval_requests | Pending discount; refuses prices below cost |
| `save_customer_draft(ticket_id, recipient, subject, body, created_by)` | customer_drafts | Draft to the ticket requester only; never sent |
| `update_ticket(ticket_id, status, note, updated_by)` | tickets | Status plus an appended, dated note |

**Human only (hidden from all agents by the backend)**

| Tool | Writes | Purpose |
|---|---|---|
| `decide_approval_request(request_id, decision, decided_by)` | approval_requests | Approve or reject; agent names are refused |
| `execute_approved_payment(request_id)` | cash_accounts, payments, invoices / leases, approval_requests | Pays only if approved; refuses negative balances; marks the invoice paid or moves rent forward a month |
| `place_approved_purchase_order(request_id)` | cash_accounts, payments, approval_requests | Simulated **prepaid** order: debits checking and adds a `payments` row (kind `purchase_order`); refuses if the vendor has an open invoice or cash is short |

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python mcp_server/server.py      # stdio server (Claude Code starts it via .mcp.json)
```
