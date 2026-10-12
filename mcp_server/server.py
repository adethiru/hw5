"""Campus Customs MCP server (FastMCP).

The single source of shop facts and shop actions for every agent on the Campus
Customs team. All tools operate on the WORKING database copy,
data/campus_customs_new.db. The original data/campus_customs.db is never opened
here, so it remains a clean reset point.

Shop rules enforced here (not just in prompts):
  * "Today" is desk.date_today, never the computer clock.
  * A vendor with any open invoice will not ship new product.
  * Payments need a human-approved request; agents can only *request*.
  * Purchase orders are PREPAID: placing an approved PO debits checking.
  * Pay / PO tools refuse if cash would go negative. Cash only goes out.
  * Amounts come from the database (invoice amount, lease rent, unit cost),
    never from free text, so agents cannot invent figures.
  * Customer messages are saved as drafts only - nothing is ever sent.

Board tables `approval_requests` and `customer_drafts` are created on demand
in the working DB (CREATE TABLE IF NOT EXISTS), so a reset from the original
file simply starts with an empty board.

Run:  python mcp_server/server.py   (stdio transport)
"""

from __future__ import annotations

import calendar
import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

try:  # mcp 1.x - FastMCP (pinned in requirements.txt: mcp<2)
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # mcp 2.x renamed FastMCP -> MCPServer (same decorator API)
    from mcp.server.mcpserver import MCPServer as FastMCP

DB_PATH = Path(
    os.environ.get(
        "CAMPUS_DB_PATH",
        Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db",
    )
)

mcp = FastMCP("campus-customs")

TICKET_STATUSES = ("open", "in_progress", "awaiting_approval", "blocked", "resolved")
AGENT_NAMES = ("boss", "inventory", "accounting", "facilities", "customer_service")

# Tools only a human (via the dashboard/backend) may call. The backend removes
# these from every agent's toolset; the tools also re-check request status.
HUMAN_ONLY_TOOLS = (
    "decide_approval_request",
    "execute_approved_payment",
    "place_approved_purchase_order",
)

BOARD_SCHEMA = """
CREATE TABLE IF NOT EXISTS approval_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER,
    kind TEXT NOT NULL,              -- payment | purchase_order | price_override
    target_type TEXT,                -- invoice | lease | vendor | sku
    target_id TEXT,
    amount REAL NOT NULL,
    details TEXT NOT NULL,           -- JSON
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,      -- agent name
    status TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|executed
    created_at TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    decision_note TEXT,
    executed_at TEXT,
    payment_id INTEGER
);
CREATE TABLE IF NOT EXISTS customer_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    created_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',    -- drafts are never sent
    created_at TEXT NOT NULL
);
"""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Working database not found at {DB_PATH}. "
            "Copy data/campus_customs.db to data/campus_customs_new.db first."
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(BOARD_SCHEMA)
    return conn


def _shop_today(conn: sqlite3.Connection) -> date:
    """The shop's 'today' comes from desk.date_today, never the system clock."""
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    if row is None:
        raise ValueError("desk table has no date_today row.")
    return date.fromisoformat(row["date_today"])


def _now() -> str:
    """Wall-clock timestamp for audit fields only (never for business dates)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _add_one_month(d: date) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _open_invoices_for_vendor(conn, vendor_id: int, today: date) -> list[dict]:
    rows = conn.execute(
        "SELECT id, amount, due_date, description FROM invoices "
        "WHERE vendor_id = ? AND status = 'open' ORDER BY due_date",
        (vendor_id,),
    ).fetchall()
    out = []
    for inv in rows:
        days_over = (today - date.fromisoformat(inv["due_date"])).days
        out.append(
            {
                "invoice_id": inv["id"],
                "amount": inv["amount"],
                "due_date": inv["due_date"],
                "description": inv["description"],
                "is_overdue": days_over > 0,
                "days_overdue": max(days_over, 0),
            }
        )
    return out


def _pending_total(conn) -> float:
    r = conn.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM approval_requests "
        "WHERE kind IN ('payment','purchase_order') AND status IN ('pending','approved')"
    ).fetchone()
    return round(r["s"], 2)


def _approval_row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["details"] = json.loads(d["details"]) if d.get("details") else {}
    return d


def _ticket_exists(conn, ticket_id: Optional[int]) -> bool:
    if ticket_id is None:
        return True
    return conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is not None


def _check_agent(name: str) -> Optional[str]:
    if name not in AGENT_NAMES:
        return f"requested_by/created_by must be one of {AGENT_NAMES}, got {name!r}."
    return None


# =========================================================================== #
# READ TOOLS
# =========================================================================== #
@mcp.tool()
def list_tickets(status: Optional[str] = "open") -> dict:
    """List tickets on the board (default: only status='open').

    Args:
        status: open | in_progress | awaiting_approval | blocked | resolved,
            or "all" for every ticket.

    Returns shop_today and each ticket's id, type, requester, subject, sku,
    size, qty, lease_id, invoice_id, status, notes, created_at.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        if status in (None, "all"):
            rows = conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE status = ? ORDER BY id", (status,)
            ).fetchall()
        return {"shop_today": today.isoformat(), "count": len(rows), "tickets": [dict(r) for r in rows]}


@mcp.tool()
def get_ticket(ticket_id: int) -> dict:
    """Get one ticket plus every row it links to, and its board activity.

    Follows the ticket's foreign keys: invoice_id -> invoices (+ vendor),
    lease_id -> leases, sku/size -> inventory + pricing. Also returns any
    approval requests and customer drafts already filed for this ticket.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        t = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            ids = [r["id"] for r in conn.execute("SELECT id FROM tickets ORDER BY id")]
            return {"found": False, "error": f"No ticket {ticket_id}.", "known_ticket_ids": ids}
        t = dict(t)
        linked: dict = {}
        if t["invoice_id"] is not None:
            inv = conn.execute(
                "SELECT i.*, v.name AS vendor_name, v.specialty, v.lead_days "
                "FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
                (t["invoice_id"],),
            ).fetchone()
            if inv:
                inv = dict(inv)
                days_over = (today - date.fromisoformat(inv["due_date"])).days
                inv["is_overdue"] = inv["status"] == "open" and days_over > 0
                inv["days_overdue"] = max(days_over, 0) if inv["status"] == "open" else 0
                linked["invoice"] = inv
        if t["lease_id"] is not None:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (t["lease_id"],)).fetchone()
            if lease:
                linked["lease"] = dict(lease)
        if t["sku"]:
            q = "SELECT * FROM inventory WHERE sku = ?" + (" AND size = ?" if t["size"] else "")
            args = (t["sku"], t["size"]) if t["size"] else (t["sku"],)
            linked["inventory"] = [dict(r) for r in conn.execute(q, args)]
            p = conn.execute("SELECT * FROM pricing WHERE sku = ?", (t["sku"],)).fetchone()
            if p:
                linked["pricing"] = dict(p)
        approvals = [
            _approval_row(r)
            for r in conn.execute(
                "SELECT * FROM approval_requests WHERE ticket_id = ? ORDER BY id", (ticket_id,)
            )
        ]
        drafts = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM customer_drafts WHERE ticket_id = ? ORDER BY id", (ticket_id,)
            )
        ]
        return {
            "found": True,
            "shop_today": today.isoformat(),
            "ticket": t,
            "linked": linked,
            "approval_requests": approvals,
            "customer_drafts": drafts,
        }


@mcp.tool()
def check_inventory_stock(
    sku: str, size: Optional[str] = None, qty_needed: Optional[int] = None
) -> dict:
    """Look up on-hand stock for a SKU (optionally one size) in the inventory table.

    Args:
        sku: Product SKU, e.g. "CC-TEE-WHITE".
        size: Size code, e.g. "S", "M", "L", "XL", "OS". Omit to list every size.
        qty_needed: Units the ticket asks for. If given (with size), reports the
            shortfall = max(qty_needed - on_hand, 0).
    """
    with _connect() as conn:
        if size:
            rows = conn.execute(
                "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
                (sku, size),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? ORDER BY rowid",
                (sku,),
            ).fetchall()
        if not rows:
            known = conn.execute("SELECT sku, size FROM inventory ORDER BY rowid").fetchall()
            return {
                "found": False,
                "error": f"No inventory row for sku={sku!r}" + (f", size={size!r}" if size else ""),
                "known_sku_sizes": [f"{r['sku']} / {r['size']}" for r in known],
            }
        items = [dict(r) for r in rows]
        result: dict = {"found": True, "items": items}
        if qty_needed is not None and size:
            on_hand = items[0]["qty"]
            shortfall = max(qty_needed - on_hand, 0)
            result.update(
                {
                    "qty_needed": qty_needed,
                    "on_hand": on_hand,
                    "shortfall": shortfall,
                    "can_fill_from_stock": shortfall == 0,
                }
            )
        return result


@mcp.tool()
def check_vendor_status(vendor_id: Optional[int] = None) -> dict:
    """Report each vendor's specialty, lead time, unpaid invoices and ship status.

    Shop rule: a vendor will NOT ship new product while it has any open invoice.
    Overdue = open and due_date < desk.date_today.

    Args:
        vendor_id: vendors.id. Omit to list all vendors (pick a restock vendor
            by `specialty`; there is no SKU-to-vendor table).

    Returns per vendor: vendor_id, name, specialty, lead_days, open_invoices,
    total_open_amount, will_ship_new_product, earliest_arrival_if_ordered_today
    (desk.date_today + lead_days; only reachable once open invoices are paid).
    """
    with _connect() as conn:
        today = _shop_today(conn)
        if vendor_id is not None:
            vendors = conn.execute(
                "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?", (vendor_id,)
            ).fetchall()
            if not vendors:
                return {"found": False, "error": f"No vendor with id={vendor_id}."}
        else:
            vendors = conn.execute(
                "SELECT id, name, specialty, lead_days FROM vendors ORDER BY id"
            ).fetchall()
        out = []
        for v in vendors:
            open_invoices = _open_invoices_for_vendor(conn, v["id"], today)
            out.append(
                {
                    "vendor_id": v["id"],
                    "name": v["name"],
                    "specialty": v["specialty"],
                    "lead_days": v["lead_days"],
                    "open_invoices": open_invoices,
                    "total_open_amount": round(sum(i["amount"] for i in open_invoices), 2),
                    "will_ship_new_product": len(open_invoices) == 0,
                    "earliest_arrival_if_ordered_today": (
                        today + timedelta(days=v["lead_days"])
                    ).isoformat(),
                }
            )
        return {"found": True, "shop_today": today.isoformat(), "vendors": out}


@mcp.tool()
def get_lease_rent_status(lease_id: int) -> dict:
    """Return rent details for a lease plus the cash available to pay it.

    Returns space_name, landlord, monthly_rent, next_due, days_until_due
    (negative = overdue, from desk.date_today), is_overdue, and each cash
    account's balance and balance_after_rent. Does NOT pay.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        lease = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        if lease is None:
            return {"found": False, "error": f"No lease with id={lease_id}."}
        days_until = (date.fromisoformat(lease["next_due"]) - today).days
        rent = lease["monthly_rent"]
        accounts = [
            {
                "account": a["name"],
                "balance": a["balance"],
                "as_of": a["date"],
                "covers_rent": a["balance"] >= rent,
                "balance_after_rent": round(a["balance"] - rent, 2),
            }
            for a in conn.execute("SELECT name, balance, date FROM cash_accounts ORDER BY name")
        ]
        return {
            "found": True,
            "shop_today": today.isoformat(),
            "lease_id": lease["id"],
            "space_name": lease["space_name"],
            "landlord": lease["landlord"],
            "monthly_rent": rent,
            "next_due": lease["next_due"],
            "days_until_due": days_until,
            "is_overdue": days_until < 0,
            "notes": lease["notes"],
            "cash_accounts": accounts,
        }


@mcp.tool()
def get_pricing_and_margin(
    sku: str, proposed_unit_price: Optional[float] = None, qty: Optional[int] = None
) -> dict:
    """Return unit_cost and list_price for a SKU and compute margins.

    Args:
        sku: Product SKU.
        proposed_unit_price: Optional discounted price to evaluate.
        qty: Optional quantity for order totals.

    Returns unit_cost, list_price, margin at list (dollars and %), and, if a
    proposed price is given, discount_pct, margin at that price and whether it
    is below cost. With qty: revenue, cost and profit totals.
    """
    with _connect() as conn:
        p = conn.execute(
            "SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
        if p is None:
            skus = [r["sku"] for r in conn.execute("SELECT sku FROM pricing ORDER BY sku")]
            return {"found": False, "error": f"No pricing for sku={sku!r}.", "known_skus": skus}
        cost, lp = p["unit_cost"], p["list_price"]

        def margin(price: float) -> dict:
            return {
                "unit_price": round(price, 2),
                "margin_per_unit": round(price - cost, 2),
                "margin_pct": round((price - cost) / price * 100, 1) if price else None,
            }

        out = {"found": True, "sku": sku, "unit_cost": cost, "list_price": lp, "at_list": margin(lp)}
        if qty:
            out["at_list"].update(
                {"qty": qty, "revenue": round(lp * qty, 2), "cost": round(cost * qty, 2),
                 "profit": round((lp - cost) * qty, 2)}
            )
        if proposed_unit_price is not None:
            m = margin(proposed_unit_price)
            m["discount_pct"] = round((lp - proposed_unit_price) / lp * 100, 1)
            m["below_cost"] = proposed_unit_price < cost
            if qty:
                m.update(
                    {"qty": qty, "revenue": round(proposed_unit_price * qty, 2),
                     "cost": round(cost * qty, 2),
                     "profit": round((proposed_unit_price - cost) * qty, 2)}
                )
            out["at_proposed"] = m
        return out


@mcp.tool()
def get_cash_position() -> dict:
    """Snapshot of money: balances, what is owed, and what is already queued.

    Returns cash_accounts balances, all open invoices (with overdue flags and
    vendor names), each lease's rent and next_due, the total of payment
    requests already pending/approved, and cash_after_pending_payments.
    Remember: no revenue is modeled, cash only goes out.
    """
    with _connect() as conn:
        today = _shop_today(conn)
        accounts = [dict(r) for r in conn.execute("SELECT name, balance, date FROM cash_accounts")]
        total_cash = round(sum(a["balance"] for a in accounts), 2)
        invoices = []
        for r in conn.execute(
            "SELECT i.id, i.vendor_id, v.name vendor_name, i.amount, i.due_date, i.description "
            "FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.status = 'open' ORDER BY i.due_date"
        ):
            days_over = (today - date.fromisoformat(r["due_date"])).days
            invoices.append({**dict(r), "is_overdue": days_over > 0, "days_overdue": max(days_over, 0)})
        leases = []
        for r in conn.execute("SELECT id, space_name, landlord, monthly_rent, next_due FROM leases"):
            leases.append({**dict(r), "days_until_due": (date.fromisoformat(r["next_due"]) - today).days})
        pending = _pending_total(conn)
        return {
            "shop_today": today.isoformat(),
            "cash_accounts": accounts,
            "total_cash": total_cash,
            "open_invoices": invoices,
            "open_invoice_total": round(sum(i["amount"] for i in invoices), 2),
            "leases": leases,
            "pending_payment_requests_total": pending,
            "cash_after_pending_payments": round(total_cash - pending, 2),
        }


@mcp.tool()
def list_approval_requests(status: Optional[str] = "pending", ticket_id: Optional[int] = None) -> dict:
    """List approval requests on the board (default: pending).

    Args:
        status: pending | approved | rejected | executed | "all".
        ticket_id: Optional filter.
    """
    with _connect() as conn:
        sql, args = "SELECT * FROM approval_requests WHERE 1=1", []
        if status not in (None, "all"):
            sql += " AND status = ?"
            args.append(status)
        if ticket_id is not None:
            sql += " AND ticket_id = ?"
            args.append(ticket_id)
        rows = [_approval_row(r) for r in conn.execute(sql + " ORDER BY id", args)]
        return {"count": len(rows), "approval_requests": rows}


@mcp.tool()
def list_customer_drafts(ticket_id: Optional[int] = None) -> dict:
    """List customer message drafts on the board (optionally for one ticket)."""
    with _connect() as conn:
        if ticket_id is None:
            rows = conn.execute("SELECT * FROM customer_drafts ORDER BY id").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM customer_drafts WHERE ticket_id = ? ORDER BY id", (ticket_id,)
            ).fetchall()
        return {"count": len(rows), "customer_drafts": [dict(r) for r in rows]}


# =========================================================================== #
# AGENT WRITE TOOLS (board only - no money moves)
# =========================================================================== #
@mcp.tool()
def request_payment_approval(
    target_type: Literal["invoice", "lease"],
    target_id: int,
    ticket_id: Optional[int],
    reason: str,
    requested_by: str,
    account: str = "checking",
) -> dict:
    """File a PENDING payment request for a human to approve. Moves no money.

    The amount is taken from the database (invoice.amount for an open invoice,
    leases.monthly_rent for a lease) - agents cannot set it. Refuses duplicates
    (an existing pending/approved request for the same target) and paid invoices.

    Args:
        target_type: "invoice" or "lease".
        target_id: invoices.id or leases.id.
        ticket_id: Ticket this payment unlocks (or null).
        reason: Why this should be paid now (shown to the human approver).
        requested_by: Agent name filing the request (normally "accounting").
        account: cash_accounts.name to pay from (default "checking").
    """
    with _connect() as conn:
        if err := _check_agent(requested_by):
            return {"ok": False, "error": err}
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket {ticket_id}."}
        today = _shop_today(conn)
        acct = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if acct is None:
            return {"ok": False, "error": f"No cash account {account!r}."}

        if target_type == "invoice":
            inv = conn.execute(
                "SELECT i.*, v.name vendor_name FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
                (target_id,),
            ).fetchone()
            if inv is None:
                return {"ok": False, "error": f"No invoice {target_id}."}
            if inv["status"] != "open":
                return {"ok": False, "error": f"Invoice {target_id} is '{inv['status']}', not open."}
            amount = inv["amount"]
            details = {
                "payee": inv["vendor_name"], "vendor_id": inv["vendor_id"],
                "due_date": inv["due_date"], "description": inv["description"],
                "days_overdue": max((today - date.fromisoformat(inv["due_date"])).days, 0),
                "account": account,
            }
        else:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (target_id,)).fetchone()
            if lease is None:
                return {"ok": False, "error": f"No lease {target_id}."}
            amount = lease["monthly_rent"]
            details = {
                "payee": lease["landlord"], "space_name": lease["space_name"],
                "due_date": lease["next_due"],
                "days_until_due": (date.fromisoformat(lease["next_due"]) - today).days,
                "account": account,
            }

        dup = conn.execute(
            "SELECT id, status FROM approval_requests WHERE kind='payment' AND target_type=? "
            "AND target_id=? AND status IN ('pending','approved')",
            (target_type, str(target_id)),
        ).fetchone()
        if dup:
            return {"ok": False, "error": f"Duplicate: request #{dup['id']} is already {dup['status']}.",
                    "existing_request_id": dup["id"]}

        pending = _pending_total(conn)
        details["cash_balance_now"] = acct["balance"]
        details["already_queued_payments"] = pending
        details["balance_if_all_queued_paid"] = round(acct["balance"] - pending - amount, 2)
        cur = conn.execute(
            "INSERT INTO approval_requests (ticket_id, kind, target_type, target_id, amount, details, "
            "reason, requested_by, status, created_at) VALUES (?,?,?,?,?,?,?,?, 'pending', ?)",
            (ticket_id, "payment", target_type, str(target_id), amount, json.dumps(details),
             reason, requested_by, _now()),
        )
        warn = None
        if details["balance_if_all_queued_paid"] < 0:
            warn = "Cash cannot cover this plus already-queued payments; the pay tool will refuse whichever runs out."
        return {"ok": True, "request_id": cur.lastrowid, "status": "pending", "amount": amount,
                "details": details, "warning": warn,
                "note": "Awaiting human approval. No money has moved."}


@mcp.tool()
def request_purchase_order_approval(
    vendor_id: int, sku: str, size: str, qty: int, ticket_id: Optional[int],
    reason: str, requested_by: str,
) -> dict:
    """File a PENDING restock purchase order for human approval. Places nothing.

    POs are PREPAID: once a human approves, placing it debits checking.
    Cost = qty x pricing.unit_cost (from the DB). Reports whether the vendor
    is currently blocked by an open invoice and the expected arrival date.
    """
    with _connect() as conn:
        if err := _check_agent(requested_by):
            return {"ok": False, "error": err}
        if qty <= 0:
            return {"ok": False, "error": "qty must be positive."}
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket {ticket_id}."}
        today = _shop_today(conn)
        v = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if v is None:
            return {"ok": False, "error": f"No vendor {vendor_id}."}
        inv_row = conn.execute("SELECT 1 FROM inventory WHERE sku=? AND size=?", (sku, size)).fetchone()
        p = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if inv_row is None or p is None:
            return {"ok": False, "error": f"Unknown sku/size {sku}/{size} or no pricing."}
        open_inv = _open_invoices_for_vendor(conn, vendor_id, today)
        amount = round(qty * p["unit_cost"], 2)
        details = {
            "vendor_name": v["name"], "vendor_specialty": v["specialty"], "lead_days": v["lead_days"],
            "sku": sku, "size": size, "qty": qty, "unit_cost": p["unit_cost"],
            "vendor_blocked_by_open_invoices": [i["invoice_id"] for i in open_inv],
            "earliest_arrival_if_placed_today": (today + timedelta(days=v["lead_days"])).isoformat(),
            "prepaid": True,
        }
        bal = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()
        pending = _pending_total(conn)
        details["cash_balance_now"] = bal["balance"] if bal else 0
        details["already_queued_payments"] = pending
        details["balance_if_all_queued_paid"] = round(details["cash_balance_now"] - pending - amount, 2)
        cur = conn.execute(
            "INSERT INTO approval_requests (ticket_id, kind, target_type, target_id, amount, details, "
            "reason, requested_by, status, created_at) VALUES (?,?,?,?,?,?,?,?, 'pending', ?)",
            (ticket_id, "purchase_order", "vendor", str(vendor_id), amount, json.dumps(details),
             reason, requested_by, _now()),
        )
        return {"ok": True, "request_id": cur.lastrowid, "status": "pending", "amount": amount,
                "details": details,
                "warning": " ".join(w for w in [
                    "Vendor will not ship until open invoices are paid." if open_inv else "",
                    "Cash cannot cover this plus already-queued payments." if details["balance_if_all_queued_paid"] < 0 else "",
                ] if w) or None,
                "note": "Awaiting human approval. POs are prepaid: approving debits checking. Nothing ordered yet."}


@mcp.tool()
def request_price_override_approval(
    ticket_id: int, sku: str, qty: int, proposed_unit_price: float, reason: str, requested_by: str,
) -> dict:
    """File a PENDING discount / price override for human approval.

    Refuses prices below pricing.unit_cost. Records list price, discount % and
    margin so the human sees the trade-off.
    """
    with _connect() as conn:
        if err := _check_agent(requested_by):
            return {"ok": False, "error": err}
        if not _ticket_exists(conn, ticket_id):
            return {"ok": False, "error": f"No ticket {ticket_id}."}
        p = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if p is None:
            return {"ok": False, "error": f"No pricing for {sku}."}
        if proposed_unit_price < p["unit_cost"]:
            return {"ok": False, "error": f"Refused: ${proposed_unit_price} is below unit cost ${p['unit_cost']}."}
        lp = p["list_price"]
        details = {
            "sku": sku, "qty": qty, "unit_cost": p["unit_cost"], "list_price": lp,
            "proposed_unit_price": proposed_unit_price,
            "discount_pct": round((lp - proposed_unit_price) / lp * 100, 1),
            "margin_pct": round((proposed_unit_price - p["unit_cost"]) / proposed_unit_price * 100, 1),
            "order_revenue": round(proposed_unit_price * qty, 2),
            "revenue_given_up_vs_list": round((lp - proposed_unit_price) * qty, 2),
        }
        amount = details["order_revenue"]
        cur = conn.execute(
            "INSERT INTO approval_requests (ticket_id, kind, target_type, target_id, amount, details, "
            "reason, requested_by, status, created_at) VALUES (?,?,?,?,?,?,?,?, 'pending', ?)",
            (ticket_id, "price_override", "sku", sku, amount, json.dumps(details), reason, requested_by, _now()),
        )
        return {"ok": True, "request_id": cur.lastrowid, "status": "pending", "details": details,
                "note": "Awaiting human approval. Price not changed."}


@mcp.tool()
def save_customer_draft(ticket_id: int, recipient: str, subject: str, body: str, created_by: str) -> dict:
    """Save a customer message as a DRAFT on the board. Nothing is ever sent.

    The recipient must be the ticket's requester (no messaging other people).
    """
    with _connect() as conn:
        if err := _check_agent(created_by):
            return {"ok": False, "error": err}
        t = conn.execute("SELECT requester FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"ok": False, "error": f"No ticket {ticket_id}."}
        if recipient.strip().lower() != t["requester"].strip().lower():
            return {"ok": False, "error": f"Recipient must be the ticket requester {t['requester']!r}."}
        cur = conn.execute(
            "INSERT INTO customer_drafts (ticket_id, recipient, subject, body, created_by, status, created_at) "
            "VALUES (?,?,?,?,?, 'draft', ?)",
            (ticket_id, t["requester"], subject, body, created_by, _now()),
        )
        return {"ok": True, "draft_id": cur.lastrowid, "status": "draft",
                "note": "Saved to the board as a draft. Not sent."}


@mcp.tool()
def update_ticket(ticket_id: int, status: str, note: str, updated_by: str) -> dict:
    """Set a ticket's status and append a dated note (original notes are kept).

    Args:
        status: open | in_progress | awaiting_approval | blocked | resolved.
        note: Short summary of what was decided / what is pending.
        updated_by: Agent name (normally "boss"), or "system" when the backend
            closes a ticket after a finished run.
    """
    with _connect() as conn:
        if updated_by != "system" and (err := _check_agent(updated_by)):
            return {"ok": False, "error": err}
        if status not in TICKET_STATUSES:
            return {"ok": False, "error": f"status must be one of {TICKET_STATUSES}."}
        t = conn.execute("SELECT status, notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"ok": False, "error": f"No ticket {ticket_id}."}
        today = _shop_today(conn).isoformat()
        new_notes = (t["notes"] or "") + f"\n[{today} {updated_by}] {note}"
        conn.execute("UPDATE tickets SET status = ?, notes = ? WHERE id = ?", (status, new_notes, ticket_id))
        return {"ok": True, "ticket_id": ticket_id, "old_status": t["status"], "new_status": status}


# =========================================================================== #
# HUMAN-ONLY TOOLS (removed from every agent's toolset by the backend)
# =========================================================================== #
@mcp.tool()
def decide_approval_request(
    request_id: int, decision: Literal["approved", "rejected"], decided_by: str, note: str = ""
) -> dict:
    """HUMAN ONLY. Approve or reject a pending request. Moves no money by itself.

    decided_by must be a human name - agent names are refused.
    """
    if not decided_by.strip() or decided_by.strip().lower() in AGENT_NAMES or "agent" in decided_by.lower():
        return {"ok": False, "error": "decided_by must be a human approver, not an agent."}
    with _connect() as conn:
        r = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,)).fetchone()
        if r is None:
            return {"ok": False, "error": f"No request {request_id}."}
        if r["status"] != "pending":
            return {"ok": False, "error": f"Request {request_id} is '{r['status']}', not pending."}
        conn.execute(
            "UPDATE approval_requests SET status=?, decided_by=?, decided_at=?, decision_note=? WHERE id=?",
            (decision, decided_by.strip(), _now(), note, request_id),
        )
        return {"ok": True, "request_id": request_id, "status": decision}


@mcp.tool()
def execute_approved_payment(request_id: int) -> dict:
    """HUMAN ONLY. Pay a human-APPROVED payment request.

    Refuses unless the request is kind=payment and status=approved. Refuses if
    the cash account balance is lower than the amount (no negative balances).
    On success, in one transaction: debits cash_accounts (date = desk date),
    inserts a payments row (approved_by = the human), marks the invoice 'paid'
    or advances leases.next_due by one month, and marks the request executed.
    """
    conn = _connect()
    try:
        today = _shop_today(conn).isoformat()
        r = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,)).fetchone()
        if r is None:
            return {"ok": False, "error": f"No request {request_id}."}
        if r["kind"] != "payment":
            return {"ok": False, "error": f"Request {request_id} is a {r['kind']}, not a payment."}
        if r["status"] != "approved" or not r["decided_by"]:
            return {"ok": False, "error": f"Refused: request {request_id} is '{r['status']}'. Human approval required."}
        details = json.loads(r["details"])
        account = details.get("account", "checking")
        amount = r["amount"]
        target_id = int(r["target_id"])

        conn.execute("BEGIN IMMEDIATE")
        bal = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if bal is None:
            conn.rollback()
            return {"ok": False, "error": f"No cash account {account!r}."}
        if bal["balance"] < amount:
            conn.rollback()
            return {"ok": False, "error": f"Refused: {account} has ${bal['balance']:.2f}, payment is ${amount:.2f}. "
                    "No negative balances allowed.", "balance": bal["balance"], "amount": amount}

        if r["target_type"] == "invoice":
            inv = conn.execute("SELECT status, amount FROM invoices WHERE id = ?", (target_id,)).fetchone()
            if inv is None or inv["status"] != "open":
                conn.rollback()
                return {"ok": False, "error": f"Invoice {target_id} is not open; nothing to pay."}
            kind = "invoice"
        else:
            lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (target_id,)).fetchone()
            if lease is None:
                conn.rollback()
                return {"ok": False, "error": f"No lease {target_id}."}
            kind = "rent"

        new_bal = round(bal["balance"] - amount, 2)
        conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?", (new_bal, today, account))
        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?,?,?,?,?,?)",
            (kind, target_id, amount, account, today, r["decided_by"]),
        )
        payment_id = cur.lastrowid
        result: dict = {}
        if kind == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (target_id,))
            result["invoice_status"] = "paid"
        else:
            old = date.fromisoformat(lease["next_due"])
            new_due = _add_one_month(old).isoformat()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (new_due, target_id))
            result["lease_next_due"] = {"old": lease["next_due"], "new": new_due}
        conn.execute(
            "UPDATE approval_requests SET status='executed', executed_at=?, payment_id=? WHERE id=?",
            (_now(), payment_id, request_id),
        )
        conn.commit()
        return {"ok": True, "payment_id": payment_id, "kind": kind, "ref_id": target_id, "amount": amount,
                "account": account, "balance_before": bal["balance"], "balance_after": new_bal,
                "approved_by": r["decided_by"], "paid_at": today, **result}
    except Exception as e:  # pragma: no cover - surface DB errors to caller
        conn.rollback()
        return {"ok": False, "error": f"Payment failed and was rolled back: {e}"}
    finally:
        conn.close()


@mcp.tool()
def place_approved_purchase_order(request_id: int) -> dict:
    """HUMAN ONLY. Place and PREPAY a human-APPROVED purchase order (simulated).

    Purchase orders are prepaid in this shop: placing one is a cash outflow.
    Refuses unless status=approved by a human; refuses if the vendor still has
    any open invoice (vendor will not ship); refuses if checking cannot cover
    qty x unit_cost (no negative balances). On success, in one transaction:
    debits cash_accounts (date = desk date), inserts a payments row
    (kind='purchase_order', ref_id = approval request id, approved_by = human)
    and marks the request executed with its payment_id. Stock is NOT added -
    goods arrive desk.date_today + lead_days. No real vendor is contacted.
    """
    conn = _connect()
    try:
        today = _shop_today(conn)
        r = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,)).fetchone()
        if r is None:
            return {"ok": False, "error": f"No request {request_id}."}
        if r["kind"] != "purchase_order":
            return {"ok": False, "error": f"Request {request_id} is a {r['kind']}, not a purchase order."}
        if r["status"] != "approved" or not r["decided_by"]:
            return {"ok": False, "error": f"Refused: request {request_id} is '{r['status']}'. Human approval required."}
        vendor_id = int(r["target_id"])
        open_inv = _open_invoices_for_vendor(conn, vendor_id, today)
        if open_inv:
            return {"ok": False, "error": "Refused: vendor has open invoices and will not ship.",
                    "open_invoices": open_inv}
        amount = r["amount"]
        account = "checking"
        conn.execute("BEGIN IMMEDIATE")
        bal = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if bal is None or bal["balance"] < amount:
            conn.rollback()
            have = bal["balance"] if bal else 0
            return {"ok": False, "error": f"Refused: {account} has ${have:.2f}, purchase order is ${amount:.2f}. "
                    "No negative balances allowed.", "balance": have, "amount": amount}
        new_bal = round(bal["balance"] - amount, 2)
        conn.execute("UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
                     (new_bal, today.isoformat(), account))
        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?,?,?,?,?,?)",
            ("purchase_order", request_id, amount, account, today.isoformat(), r["decided_by"]),
        )
        payment_id = cur.lastrowid
        conn.execute("UPDATE approval_requests SET status='executed', executed_at=?, payment_id=? WHERE id=?",
                     (_now(), payment_id, request_id))
        conn.commit()
        v = conn.execute("SELECT name, lead_days FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        details = json.loads(r["details"])
        return {"ok": True, "request_id": request_id, "payment_id": payment_id, "vendor": v["name"],
                "sku": details.get("sku"), "size": details.get("size"), "qty": details.get("qty"),
                "amount": amount, "balance_before": bal["balance"], "balance_after": new_bal,
                "approved_by": r["decided_by"],
                "expected_arrival": (today + timedelta(days=v["lead_days"])).isoformat(),
                "note": "Simulated prepaid order. No real vendor was contacted; stock arrives later."}
    except Exception as e:  # pragma: no cover
        conn.rollback()
        return {"ok": False, "error": f"Purchase order failed and was rolled back: {e}"}
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run()
