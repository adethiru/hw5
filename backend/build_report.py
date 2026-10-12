"""Build the Problem 9 deliverables from a REAL run (no model calls).

    python -m backend.build_report

Reads ONLY real evidence:
  * output/audit_trail.json  - every agent-loop step, delegation and human action
  * data/campus_customs_new.db - tickets, approval_requests, customer_drafts,
                                 payments, cash_accounts (after your approvals)
  * data/campus_customs.db     - starting checking balance (the reset source)
  * output/screenshots/ticket_101.png, _102.png, _103.png (your board screenshots)

Writes:
  * output/desk_tickets.html  - fills each ticket's ACTUAL section + the Cash tab
  * output/resolved_tickets.json
  * output/resolved_board.html - screenshots of the React board per ticket

Cash math is computed from the payments table and CHECKED against
cash_accounts: start - sum(payments) must equal the ending balance, or the
script stops with an error (it never writes a cash table that doesn't add up).
"""

from __future__ import annotations

import base64
import html
import json
import re
import sqlite3
import sys
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL_DB = ROOT / "data" / "campus_customs.db"
WORKING_DB = ROOT / "data" / "campus_customs_new.db"
AUDIT = ROOT / "output" / "audit_trail.json"
DESK = ROOT / "output" / "desk_tickets.html"
RESOLVED_JSON = ROOT / "output" / "resolved_tickets.json"
BOARD_HTML = ROOT / "output" / "resolved_board.html"
SHOTS = ROOT / "output" / "screenshots"
TICKETS = (101, 102, 103)
ALLOWED_MODEL = "gpt-6-luna"

LABEL = {"boss": "Boss", "inventory": "Inventory", "accounting": "Accounting",
         "facilities": "Facilities", "customer_service": "Customer Service",
         "human": "Human", "system": "System"}
CSS_CLASS = {"boss": "boss", "inventory": "inventory", "accounting": "accounting",
             "facilities": "facilities", "customer_service": "cs"}
SKIP_TOOLS = {"final_result", "delegate_task"}

# The plan from Problem 6 (Expected section), used for the Expected-vs-Actual comparison.
EXPECTED = {
    101: {"first": "inventory", "workers": ["inventory", "accounting", "customer_service"],
          "not": ["facilities"],
          "tools": ["get_ticket", "check_inventory_stock", "check_vendor_status", "get_cash_position",
                    "list_approval_requests", "request_payment_approval", "request_purchase_order_approval",
                    "list_customer_drafts", "save_customer_draft", "update_ticket"]},
    102: {"first": "facilities", "workers": ["facilities", "accounting"],
          "not": ["inventory", "customer_service"],
          "tools": ["get_ticket", "get_lease_rent_status", "get_cash_position", "list_approval_requests",
                    "request_payment_approval", "update_ticket"]},
    103: {"first": "inventory", "workers": ["inventory", "accounting", "customer_service"],
          "not": ["facilities"],
          "tools": ["get_ticket", "check_inventory_stock", "check_vendor_status", "list_approval_requests",
                    "get_pricing_and_margin", "get_cash_position", "request_price_override_approval",
                    "request_purchase_order_approval", "list_customer_drafts", "save_customer_draft",
                    "update_ticket"]},
}


def money(x: float) -> str:
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


def esc(s) -> str:
    return html.escape("" if s is None else str(s))


def die(msg: str) -> None:
    print(f"\nERROR: {msg}\n", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Load evidence
# --------------------------------------------------------------------------- #
def load_audit() -> tuple[list[dict], int]:
    if not AUDIT.exists():
        die(f"{AUDIT} not found - run the tickets first.")
    records = json.loads(AUDIT.read_text())
    resets = [i for i, r in enumerate(records) if r.get("event") == "db_reset"]
    if not resets:
        die("No db_reset record in the audit trail. Reset the DB (dashboard Reset or "
            "`python -m backend.reset_db`) before the full run, then run the tickets.")
    start = resets[-1]
    return records, start


def db_rows(conn, sql, *args):
    return [dict(r) for r in conn.execute(sql, args)]


def analyze_run(records: list[dict], ticket_id: int) -> dict | None:
    starts = [r for r in records if r.get("event") == "ticket_start" and r.get("ticket_id") == ticket_id]
    if not starts:
        return None
    run_id = starts[-1]["run_id"]
    rs = [r for r in records if r.get("run_id") == run_id]

    agents: "OrderedDict[str, dict]" = OrderedDict()

    def A(name):
        if name not in agents:
            agents[name] = {"agent": name, "steps": 0, "tools": Counter(), "asked_by": [], "delegated_to": [],
                            "report": None}
        return agents[name]

    delegations, refused, errors, models, tool_calls_in_order = [], [], [], set(), []
    decision, usage, marked_resolved_by = None, {}, None
    for r in rs:
        ev, ag = r.get("event"), r.get("agent")
        if ev == "agent_start":
            A(ag)
        elif ev == "loop_step" and r.get("node") == "model_response":
            a = A(ag)
            a["steps"] += 1
            if r.get("model_name"):
                models.add(r["model_name"])
            for p in r.get("parts", []):
                if p.get("kind") == "tool-call" and p.get("tool") not in SKIP_TOOLS:
                    a["tools"][p["tool"]] += 1
                    tool_calls_in_order.append({"agent": ag, "tool": p["tool"], "args": p.get("args")})
        elif ev == "delegation":
            delegations.append({"from": ag, "to": r.get("to_agent"), "task": r.get("task"), "depth": r.get("depth")})
            A(ag)["delegated_to"].append(r.get("to_agent"))
            A(r.get("to_agent"))["asked_by"].append(ag)
        elif ev == "delegation_refused":
            refused.append({"from": ag, "to": r.get("to_agent"), "reason": r.get("reason")})
        elif ev in ("agent_error", "ticket_error", "ticket_stopped_usage_limit"):
            errors.append({"agent": ag, "event": ev, "error": r.get("error")})
        elif ev == "agent_end":
            A(ag)["report"] = r.get("output")
            if ag == "boss":
                usage = r.get("cumulative_usage") or {}
        elif ev == "ticket_end":
            decision = r.get("decision")
        elif ev == "ticket_marked_resolved":
            marked_resolved_by = "system"

    bad_models = sorted(m for m in models if not str(m).startswith(ALLOWED_MODEL))
    return {
        "run_id": run_id, "started_at": rs[0].get("logged_at"), "ended_at": rs[-1].get("logged_at"),
        "agents": agents, "delegations": delegations, "refused": refused, "errors": errors,
        "models": sorted(models), "bad_models": bad_models, "decision": decision, "usage": usage,
        "tool_calls": tool_calls_in_order, "marked_resolved_by": marked_resolved_by,
    }


def human_actions(records: list[dict], since: int) -> list[dict]:
    out = []
    for r in records[since:]:
        if r.get("event") in ("human_decision", "human_payment", "human_purchase_order"):
            res = r.get("result") or {}
            out.append({"at": r.get("logged_at"), "event": r["event"], "ticket_id": r.get("ticket_id"),
                        "request_id": r.get("request_id"), "by": r.get("approved_by"),
                        "ok": res.get("ok") if isinstance(res, dict) else None,
                        "error": res.get("error") if isinstance(res, dict) else None})
    return out


# --------------------------------------------------------------------------- #
# Cash (the part that must be exactly right)
# --------------------------------------------------------------------------- #
def cash_ledger(conn, start_balance: float) -> dict:
    payments = db_rows(conn, "SELECT * FROM payments ORDER BY id")
    reqs = {r["payment_id"]: r for r in db_rows(conn, "SELECT * FROM approval_requests WHERE payment_id IS NOT NULL")}
    end_balance = conn.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]

    running = start_balance
    lines = []
    for p in payments:
        req = reqs.get(p["id"])
        det = json.loads(req["details"]) if req and req.get("details") else {}
        if p["kind"] == "invoice":
            what = f"Paid invoice #{p['ref_id']} to {det.get('payee', 'vendor')}" + (
                f" ({det.get('description')})" if det.get("description") else "")
        elif p["kind"] == "rent":
            what = f"Paid rent on lease #{p['ref_id']} to {det.get('payee', 'landlord')} (was due {det.get('due_date')})"
        else:
            what = (f"Prepaid purchase order (request #{p['ref_id']}): {det.get('qty')} × {det.get('sku')} "
                    f"{det.get('size')} from {det.get('vendor_name')} at {money(det.get('unit_cost', 0))}")
        before = running
        running = round(running - p["amount"], 2)
        lines.append({"payment_id": p["id"], "ticket_id": req["ticket_id"] if req else None,
                      "approval_request_id": req["id"] if req else None, "kind": p["kind"],
                      "description": what, "amount": p["amount"], "approved_by": p["approved_by"],
                      "paid_at": p["paid_at"], "balance_before": before, "balance_after": running})

    total_out = round(sum(p["amount"] for p in payments), 2)
    computed_end = round(start_balance - total_out, 2)
    if abs(computed_end - end_balance) > 0.005:
        die(f"Cash does not reconcile: start {money(start_balance)} - payments {money(total_out)} = "
            f"{money(computed_end)}, but cash_accounts.checking = {money(end_balance)}.")
    if end_balance < 0:
        die("Checking balance is negative - this should be impossible.")
    return {"start": start_balance, "end": end_balance, "total_out": total_out, "lines": lines,
            "reconciles": True}


# --------------------------------------------------------------------------- #
# HTML builders
# --------------------------------------------------------------------------- #
def agent_span(a: str) -> str:
    return f'<span class="agent {CSS_CLASS.get(a, "")}">{esc(LABEL.get(a, a))}</span>'


def actual_html(tid: int, run: dict | None, t: dict, approvals: list[dict], drafts: list[dict]) -> str:
    if run is None:
        return '<div class="placeholder">No run found for this ticket after the last reset.</div>'
    exp = EXPECTED[tid]
    deleg = run["delegations"]
    first = next((d["to"] for d in deleg if d["from"] == "boss"), None)
    workers = [a for a in run["agents"] if a != "boss"]
    tools_used = sorted({c["tool"] for c in run["tool_calls"]})
    exp_tools = set(exp["tools"])
    unexpected_agents = [a for a in exp["not"] if a in run["agents"]]
    missing_agents = [a for a in exp["workers"] if a not in run["agents"]]

    def ok(b):
        return '<span class="ok">✓ match</span>' if b else '<span class="diff">✗ differs</span>'

    flow = ['<span class="node boss">Boss</span>']
    for d in deleg:
        flow.append(f'<span class="arrow">→</span><span class="node {CSS_CLASS.get(d["to"], "")}">'
                    f'{esc(LABEL.get(d["to"], d["to"]))}</span>'
                    + (f'<span class="arrow small">(from {esc(LABEL.get(d["from"]))})</span>' if d["from"] != "boss" else ""))
    rows = []
    for i, d in enumerate(deleg, 1):
        sub_tools = sorted(run["agents"].get(d["to"], {}).get("tools", {}).keys()) if d["to"] in run["agents"] else []
        chips = "".join('<span class="chip">' + esc(x) + "</span>" for x in sub_tools)
        rows.append(f"<tr><td>{i}</td><td>{agent_span(d['from'])} → {agent_span(d['to'])}</td>"
                    f"<td>{esc(d['task'])}</td><td>{chips}</td></tr>")
    agent_rows = []
    for a, s in run["agents"].items():
        rep = s["report"] or {}
        said = rep.get("summary") or rep.get("decision") or ""
        tools = "".join(f'<span class="chip{" w" if x.startswith(("request_", "save_", "update_")) else ""}">{esc(x)}'
                        f'{" ×" + str(n) if n > 1 else ""}</span>' for x, n in s["tools"].items())
        agent_rows.append(f"<tr><td>{agent_span(a)}</td><td>{s['steps']}</td><td>{tools or '—'}</td><td>{esc(said)}</td></tr>")

    appr = "".join(f"<li>#{a['id']} {esc(a['kind'].replace('_', ' '))} {money(a['amount'])} — <b>{esc(a['status'])}</b>"
                   f"{' by ' + esc(a['decided_by']) if a.get('decided_by') else ''}</li>" for a in approvals) or "<li>None</li>"
    drf = "".join(f"<li>#{d['id']} to {esc(d['recipient'])}: “{esc(d['subject'])}” (draft, not sent)</li>" for d in drafts) or "<li>None</li>"
    dec = run["decision"] or {}
    issues = ""
    if run["refused"] or run["errors"]:
        issues = "<h4>Refusals / errors during the run</h4><ul>" + "".join(
            f"<li>{esc(x.get('from') or x.get('agent'))}: {esc(x.get('reason') or x.get('error'))}</li>"
            for x in run["refused"] + run["errors"]) + "</ul>"

    return f"""
    <div class="card first">
      <h4>Who the Boss called first: {agent_span(first) if first else "nobody (Boss worked alone)"} &nbsp; {ok(first == exp['first'])}
        <span class="legend">expected {agent_span(exp['first'])}</span></h4>
      <p class="legend">Run <code>{esc(run['run_id'])}</code> · {esc(run['started_at'])} → {esc(run['ended_at'])} ·
        model {', '.join(f'<code>{esc(m)}</code>' for m in run['models']) or '—'} ·
        {run['usage'].get('requests', '—')} model requests · {run['usage'].get('total_tokens', '—')} tokens</p>
    </div>
    <div class="card">
      <h4>Actual delegation flow ({len(deleg)} delegations; expected {len(exp['workers'])})</h4>
      <div class="flow">{''.join(flow)}<span class="arrow">→ Boss decides</span></div>
      <table><thead><tr><th>#</th><th>From → To</th><th>Task the agent wrote</th><th>Tools the receiver used</th></tr></thead>
      <tbody>{''.join(rows) or '<tr><td colspan=4>No delegations.</td></tr>'}</tbody></table>
    </div>
    <div class="card">
      <h4>Agents that worked and what they did</h4>
      <table><thead><tr><th>Agent</th><th>Steps</th><th>MCP tools called</th><th>What it reported</th></tr></thead>
      <tbody>{''.join(agent_rows)}</tbody></table>
    </div>
    <div class="card">
      <h4>Expected vs actual</h4>
      <ul>
        <li>First call: expected {agent_span(exp['first'])}, actual {agent_span(first) if first else '—'} {ok(first == exp['first'])}</li>
        <li>Specialists: expected {', '.join(agent_span(a) for a in exp['workers'])}; actual {', '.join(agent_span(a) for a in workers) or '—'}
            {ok(sorted(workers) == sorted(exp['workers']))}</li>
        <li>Agents that should have sat out but worked: {', '.join(agent_span(a) for a in unexpected_agents) or 'none ✓'}</li>
        <li>Expected agents that never worked: {', '.join(agent_span(a) for a in missing_agents) or 'none ✓'}</li>
        <li>Tools used as planned: {''.join(f'<span class="chip">{esc(x)}</span>' for x in tools_used if x in exp_tools) or '—'}</li>
        <li>Planned but not used: {''.join(f'<span class="chip">{esc(x)}</span>' for x in sorted(exp_tools - set(tools_used))) or 'none ✓'}</li>
        <li>Used but not planned: {''.join(f'<span class="chip w">{esc(x)}</span>' for x in tools_used if x not in exp_tools) or 'none ✓'}</li>
      </ul>
      {issues}
    </div>
    <div class="card">
      <h4>Outcome</h4>
      <p><b>Final status:</b> <code>{esc(t['status'])}</code>{' (set by backend after the run)' if run['marked_resolved_by'] else ''}.
         <b>Boss's call:</b> {esc(dec.get('decision', '—'))}</p>
      <div class="facts" style="grid-template-columns:1fr 1fr">
        <div><span>Approval requests</span><ul>{appr}</ul></div>
        <div><span>Customer drafts</span><ul>{drf}</ul></div>
      </div>
    </div>"""


def cash_html(cash: dict, per_ticket: dict, unpaid: list[dict], refusals: list[dict]) -> str:
    rows = [f'<tr class="start"><td colspan="4"><b>Starting checking balance (after reset)</b></td>'
            f'<td class="num"><b>{money(cash["start"])}</b></td></tr>']
    for tid in TICKETS:
        lines = per_ticket.get(tid, [])
        subtotal = round(sum(l["amount"] for l in lines), 2)
        rows.append(f'<tr class="tk"><td colspan="5"><b>Ticket {tid}</b> — cash change when resolved: '
                    f'<b>{money(-subtotal) if subtotal else "$0.00"}</b></td></tr>')
        if not lines:
            rows.append('<tr><td></td><td colspan="2">No payment or purchase executed for this ticket.</td>'
                        '<td class="num">$0.00</td><td class="num"></td></tr>')
        for l in lines:
            rows.append(f"<tr><td>pay #{l['payment_id']}</td><td>{esc(l['description'])}</td>"
                        f"<td>approved by {esc(l['approved_by'])} (request #{l['approval_request_id']})</td>"
                        f"<td class='num neg'>{money(-l['amount'])}</td><td class='num'>{money(l['balance_after'])}</td></tr>")
    orphan = per_ticket.get(None, [])
    for l in orphan:
        rows.append(f"<tr><td>pay #{l['payment_id']}</td><td>{esc(l['description'])}</td><td>no ticket</td>"
                    f"<td class='num neg'>{money(-l['amount'])}</td><td class='num'>{money(l['balance_after'])}</td></tr>")
    rows.append(f'<tr class="end"><td colspan="3"><b>Ending checking balance</b></td>'
                f'<td class="num neg"><b>{money(-cash["total_out"])}</b> total out</td>'
                f'<td class="num"><b>{money(cash["end"])}</b></td></tr>')
    unpaid_html = "".join(
        f"<li>#{u['id']} {esc(u['kind'].replace('_', ' '))} {money(u['amount'])} (ticket {u['ticket_id']}) — "
        f"<b>{esc(u['status'])}</b>: no cash moved</li>" for u in unpaid) or "<li>None</li>"
    ref_html = "".join(f"<li>Request #{r['request_id']} ({esc(r['event'].replace('human_', ''))}): {esc(r['error'])}</li>"
                       for r in refusals) or "<li>None</li>"
    return f"""
  <p class="sub">Every number below comes from the <code>payments</code> table in <code>data/campus_customs_new.db</code>.
     The starting balance comes from <code>data/campus_customs.db</code>, the reset source.
     Cash only goes out; no revenue is modeled.</p>
  <div class="card">
    <table class="cash"><thead><tr><th>Item</th><th>What and why</th><th>Human approval</th><th class="num">Change</th><th class="num">Checking after</th></tr></thead>
    <tbody>{''.join(rows)}</tbody></table>
  </div>
  <div class="card reconcile">
    <h4>Reconciliation ✓</h4>
    <p>{money(cash['start'])} start − {money(cash['total_out'])} paid out = <b>{money(cash['end'])}</b>, which equals
       <code>cash_accounts.balance</code> for <code>checking</code> in the working database. The balance never went negative.</p>
  </div>
  <div class="card">
    <h4>Requests that did not move cash</h4><ul>{unpaid_html}</ul>
    <h4>Payments or purchases the tools refused (no negative balances)</h4><ul>{ref_html}</ul>
  </div>"""


EXTRA_CSS = """
  /* report additions */
  .ok { color:#1d7a46; font-weight:700; font-size:13px; } .diff { color:#b42318; font-weight:700; font-size:13px; }
  .flow .arrow.small { font-size:12px; }
  table.cash { table-layout:auto; } table.cash th, table.cash td { width:auto !important; }
  table.cash td:first-child { white-space:nowrap; }
  table.cash td.num, table.cash th.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
  table.cash .neg { color:#b42318; } table.cash tr.start td, table.cash tr.end td { background:#f3f7fd; }
  table.cash tr.tk td { background:#fafbfd; border-top:2px solid #dfe4ec; }
  .reconcile { border-left:5px solid #1d7a46; }
  .actual .card { border-color:#d7e6d9; }
"""


def replace_between(text: str, start: str, end: str, new: str) -> str:
    pat = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pat.search(text):
        die(f"Marker {start} not found in desk_tickets.html")
    return pat.sub(lambda _m: f"{start}\n{new}\n    {end}", text, count=1)


def embed(path: Path) -> str | None:
    if not path.exists():
        return None
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def find_shot(tid: int) -> Path | None:
    for ext in ("png", "jpg", "jpeg"):
        for name in (f"ticket_{tid}.{ext}", f"board_{tid}.{ext}", f"{tid}.{ext}"):
            p = SHOTS / name
            if p.exists():
                return p
    return None


# --------------------------------------------------------------------------- #
# Reflection: objective per-ticket evaluation (Problem 10)
# --------------------------------------------------------------------------- #
def _det(a: dict) -> dict:
    try:
        return json.loads(a.get("details") or "{}")
    except json.JSONDecodeError:
        return {}


def evaluate(tid: int, run: dict | None, t: dict, approvals: list[dict], all_approvals: list[dict],
             drafts: list[dict], cash_lines: list[dict]) -> dict:
    checks: list[tuple[str, bool, str]] = []
    if run is None:
        return {"checks": [("Ticket was run after the last reset", False, "no ticket_start in audit trail")],
                "score": "0/1", "findings": []}
    exp = EXPECTED[tid]
    first = next((d["to"] for d in run["delegations"] if d["from"] == "boss"), None)
    workers = [a for a in run["agents"] if a != "boss"]
    extra = [a for a in exp["not"] if a in run["agents"]]
    missing = [a for a in exp["workers"] if a not in run["agents"]]
    tools = [c["tool"] for c in run["tool_calls"]]
    role_ok = all(
        (c["agent"] == "accounting") if c["tool"].startswith("request_") else
        (c["agent"] == "customer_service") if c["tool"] == "save_customer_draft" else
        (c["agent"] == "boss") if c["tool"] == "update_ticket" else True
        for c in run["tool_calls"])
    by_kind = lambda k: [a for a in approvals if a["kind"] == k]

    checks.append(("Routing: Boss called the planned specialist first", first == exp["first"],
                   f"planned {LABEL[exp['first']]}, actual {LABEL.get(first, 'none')}"))
    checks.append(("Efficiency: no agent the plan said should sit out", not extra,
                   "extra: " + (", ".join(LABEL[a] for a in extra) or "none")))
    checks.append(("Coverage: every planned specialist worked", not missing,
                   "missing: " + (", ".join(LABEL[a] for a in missing) or "none")))
    checks.append((f"Hand-offs within plan (+1 tolerance): {len(run['delegations'])} vs {len(exp['workers'])}",
                   len(run["delegations"]) <= len(exp["workers"]) + 1, ""))
    checks.append(("No refused delegations or errors", not run["refused"] and not run["errors"],
                   f"{len(run['refused'])} refused, {len(run['errors'])} errors"))
    checks.append(("Write tools used only by the right role", role_ok, ""))
    checks.append(("Only gpt-6-luna responded", not run["bad_models"], ", ".join(run["models"]) or "-"))
    checks.append(("Ticket ended resolved", t["status"] == "resolved", f"status = {t['status']}"))

    if tid == 101:
        pay = [a for a in by_kind("payment") if a["target_type"] == "invoice" and str(a["target_id"]) == "501"]
        po = [a for a in by_kind("purchase_order") if _det(a).get("sku") == "CC-TEE-WHITE" and _det(a).get("size") == "S"]
        checks.append(("Payment request for invoice 501 at $840.00 (from DB)",
                       any(abs(a["amount"] - 840.0) < .005 for a in pay), f"{len(pay)} filed"))
        checks.append(("PO for CC-TEE-WHITE size S from Bulldog Print Co (vendor 1)",
                       any(str(a["target_id"]) == "1" and _det(a).get("qty", 0) >= 1 for a in po), f"{len(po)} filed"))
        checks.append(("Customer draft to Tauhid Zaman", any(d["recipient"] == "Tauhid Zaman" for d in drafts), ""))
        checks.append(("No price override (not asked for)", not by_kind("price_override"), ""))
    elif tid == 102:
        pay = [a for a in by_kind("payment") if a["target_type"] == "lease" and str(a["target_id"]) == "1"]
        checks.append(("Rent payment request for lease 1 at $2,400.00 (from DB)",
                       any(abs(a["amount"] - 2400.0) < .005 for a in pay), f"{len(pay)} filed"))
        checks.append(("No customer draft (requester is the landlord)", not drafts, f"{len(drafts)} drafts"))
        checks.append(("No purchase order (no stock involved)", not by_kind("purchase_order"), ""))
    elif tid == 103:
        po_ = by_kind("purchase_order")
        ov = by_kind("price_override")
        price = _det(ov[0]).get("proposed_unit_price") if ov else None
        checks.append(("Price override filed", bool(ov), f"{len(ov)} filed"))
        checks.append(("Proposed price within policy ($49.30-$58.00: <=15% off, above $22 cost)",
                       price is not None and 49.30 - 1e-6 <= price <= 58.0, f"${price}" if price is not None else "-"))
        checks.append(("PO for the 12-unit CC-HOOD-NAVY M shortfall",
                       any(_det(a).get("sku") == "CC-HOOD-NAVY" and _det(a).get("qty", 0) >= 12 for a in po_),
                       ", ".join(f"qty {_det(a).get('qty')}" for a in po_) or "none"))
        dup = [a for a in all_approvals if a["kind"] == "payment" and a["target_type"] == "invoice"
               and str(a["target_id"]) == "501"]
        checks.append(("Did not duplicate the invoice 501 payment", len(dup) <= 1, f"{len(dup)} requests for 501 overall"))
        checks.append(("Customer draft to Yale AI Club", any(d["recipient"] == "Yale AI Club" for d in drafts), ""))

    passed = sum(1 for _, ok_, _ in checks if ok_)
    findings = []
    if first == exp["first"]:
        findings.append(f"Routing matched the plan: the Boss went to {LABEL[first]} first.")
    else:
        findings.append(f"Routing differed: the plan said {LABEL[exp['first']]} first, "
                        f"but the Boss went to {LABEL.get(first, 'nobody')}.")
    if extra:
        findings.append("Over-delegated: " + ", ".join(LABEL[a] for a in extra) + " worked although the plan had them sit out.")
    if missing:
        findings.append("Under-delegated: " + ", ".join(LABEL[a] for a in missing) + " never worked, so that part was skipped or done by another agent.")
    unplanned = sorted(set(tools) - set(exp["tools"]))
    if unplanned:
        findings.append("Tools used that the plan didn't predict: " + ", ".join(unplanned) + ".")
    unused = sorted(set(exp["tools"]) - set(tools))
    if unused:
        findings.append("Planned tools that were never called: " + ", ".join(unused) + ".")
    spent = sum(l["amount"] for l in cash_lines)
    findings.append(f"Cash effect after human approvals: {money(-spent) if spent else '$0.00'} (see the Cash tab).")
    return {"checks": checks, "score": f"{passed}/{len(checks)}", "passed": passed, "total": len(checks),
            "findings": findings, "workers": workers}


def reflect_html(tid: int, ev: dict, run: dict | None) -> str:
    items = ""
    for lbl, ok_, d in ev["checks"]:
        tail = (' — <span class="legend">' + esc(d) + "</span>") if d else ""
        items += "<li>" + ("✅" if ok_ else "❌") + " " + esc(lbl) + tail + "</li>"
    fnd = "".join(f"<li>{esc(f)}</li>" for f in ev["findings"])
    usage = (run or {}).get("usage") or {}
    return f"""<div class="runbox"><h5>From the run · <a href="#t{tid}">ticket {tid} Actual</a></h5>
      <p class="score">Score: {ev['score']} checks passed · {usage.get('requests', '-')} model requests · {usage.get('total_tokens', '-')} tokens · {len((run or {}).get('delegations', []))} hand-offs</p>
      <ul class="check">{items}</ul>
      <h5>Actual vs Expected</h5><ul>{fnd}</ul></div>"""


# --------------------------------------------------------------------------- #
def main() -> None:
    records, reset_idx = load_audit()
    since = records[reset_idx:]
    with sqlite3.connect(ORIGINAL_DB) as o:
        start_balance = o.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
    rec_start = records[reset_idx].get("starting_checking_balance")
    if rec_start is not None and abs(rec_start - start_balance) > 0.005:
        die(f"Reset record says start {rec_start}, original DB says {start_balance}.")

    conn = sqlite3.connect(WORKING_DB)
    conn.row_factory = sqlite3.Row
    tickets = {r["id"]: r for r in db_rows(conn, "SELECT * FROM tickets")}
    try:
        approvals = db_rows(conn, "SELECT * FROM approval_requests ORDER BY id")
        drafts = db_rows(conn, "SELECT * FROM customer_drafts ORDER BY id")
    except sqlite3.OperationalError:
        die("Board tables missing - the agents have not run on this working DB yet.")

    cash = cash_ledger(conn, start_balance)
    per_ticket: dict = {}
    for l in cash["lines"]:
        per_ticket.setdefault(l["ticket_id"], []).append(l)
    unpaid = [a for a in approvals if a["kind"] != "price_override" and a["status"] != "executed"]
    humans = human_actions(records, reset_idx)
    refusals = [h for h in humans if h["event"] in ("human_payment", "human_purchase_order") and h["ok"] is False]

    runs = {tid: analyze_run(since, tid) for tid in TICKETS}
    bad = {tid: r["bad_models"] for tid, r in runs.items() if r and r["bad_models"]}
    if bad:
        die(f"Model other than {ALLOWED_MODEL} found in the audit trail: {bad}")
    not_resolved = [tid for tid in TICKETS if tickets[tid]["status"] != "resolved"]
    missing = [tid for tid in TICKETS if runs[tid] is None]

    # ---- desk_tickets.html ----
    page = DESK.read_text()
    if "/* report additions */" not in page:
        page = page.replace("</style>", EXTRA_CSS + "</style>", 1)
    for tid in TICKETS:
        t = tickets[tid]
        page = replace_between(page, f"<!-- ACTUAL-{tid}-START -->", f"<!-- ACTUAL-{tid}-END -->",
                               actual_html(tid, runs[tid], t,
                                           [a for a in approvals if a["ticket_id"] == tid],
                                           [d for d in drafts if d["ticket_id"] == tid]))
    page = replace_between(page, "<!-- CASH-START -->", "<!-- CASH-END -->",
                           cash_html(cash, per_ticket, unpaid, refusals))
    evals = {}
    for tid in TICKETS:
        evals[tid] = evaluate(tid, runs[tid], tickets[tid], [a for a in approvals if a["ticket_id"] == tid],
                              approvals, [d for d in drafts if d["ticket_id"] == tid], per_ticket.get(tid, []))
        if f"<!-- REFLECT-{tid}-START -->" in page:
            page = replace_between(page, f"<!-- REFLECT-{tid}-START -->", f"<!-- REFLECT-{tid}-END -->",
                                   reflect_html(tid, evals[tid], runs[tid]))
    if "<!-- REFLECT-STATS-START -->" in page:
        rows = "".join(
            f"<tr><td><a href='#t{tid}'>{tid}</a></td><td>{len(runs[tid]['delegations']) if runs[tid] else '-'}</td>"
            f"<td>{len(runs[tid]['agents']) if runs[tid] else '-'}</td>"
            f"<td>{(runs[tid] or {}).get('usage', {}).get('requests', '-')}</td>"
            f"<td>{(runs[tid] or {}).get('usage', {}).get('total_tokens', '-')}</td>"
            f"<td>{len({c['tool'] for c in runs[tid]['tool_calls']}) if runs[tid] else '-'}</td></tr>" for tid in TICKETS)
        page = replace_between(page, "<!-- REFLECT-STATS-START -->", "<!-- REFLECT-STATS-END -->",
            '<div class="runbox"><h5>From the run · cost of the team on each ticket</h5>'
            '<table><thead><tr><th>Ticket</th><th>Hand-offs</th><th>Agent loops</th><th>Model requests</th>'
            '<th>Tokens</th><th>Distinct MCP tools</th></tr></thead><tbody>' + rows + '</tbody></table>'
            '<p class="legend">A single agent needs one loop per ticket and calls each distinct tool about once. '
            'Compare the "Agent loops" and "Tokens" columns with the "Distinct MCP tools" column.</p></div>')
    DESK.write_text(page)

    # ---- resolved_tickets.json ----
    out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "model": ALLOWED_MODEL,
           "starting_checking_balance": cash["start"], "ending_checking_balance": cash["end"],
           "cash_reconciles_with_cash_accounts": cash["reconciles"], "tickets": []}
    for tid in TICKETS:
        run, t = runs[tid], tickets[tid]
        dec = (run or {}).get("decision") or {}
        contributions = []
        for a, s in ((run or {}).get("agents") or {}).items():
            rep = s["report"] or {}
            contributions.append({
                "agent": a, "steps": s["steps"], "asked_by": s["asked_by"], "delegated_to": s["delegated_to"],
                "mcp_tools": dict(s["tools"]),
                "contribution": rep.get("summary") or rep.get("decision"),
                "recommendation": rep.get("recommendation"),
                "approval_request_ids": rep.get("approval_request_ids", []),
                "draft_ids": rep.get("draft_ids", []),
            })
        t_appr = [a for a in approvals if a["ticket_id"] == tid]
        out["tickets"].append({
            "id": tid, "type": t["type"], "requester": t["requester"], "final_status": t["status"],
            "outcome": dec.get("decision"), "run_id": (run or {}).get("run_id"),
            "agents": contributions,
            "delegations": [{"from": d["from"], "to": d["to"]} for d in (run or {}).get("delegations", [])],
            "human_approvals": [
                {"request_id": a["id"], "kind": a["kind"], "amount": a["amount"], "status": a["status"],
                 "decided_by": a["decided_by"], "decided_at": a["decided_at"], "payment_id": a["payment_id"]}
                for a in t_appr],
            "cash_change": -round(sum(l["amount"] for l in per_ticket.get(tid, [])), 2),
            "customer_drafts": [{"id": d["id"], "recipient": d["recipient"], "subject": d["subject"], "status": d["status"]}
                                for d in drafts if d["ticket_id"] == tid],
            "usage": (run or {}).get("usage"),
            "evaluation": {"score": evals[tid]["score"],
                           "checks": [{"check": c, "passed": ok_, "detail": d} for c, ok_, d in evals[tid]["checks"]],
                           "actual_vs_expected": evals[tid]["findings"]},
        })
    out["cash_ledger"] = cash["lines"]
    RESOLVED_JSON.write_text(json.dumps(out, indent=2, default=str) + "\n")

    # ---- resolved_board.html ----
    sections = []
    for t in out["tickets"]:
        shot = find_shot(t["id"])
        img = (f'<img src="{embed(shot)}" alt="React board for ticket {t["id"]}">' if shot else
               f'<div class="missing">Screenshot missing: save it as <code>output/screenshots/ticket_{t["id"]}.png</code> '
               f'and run <code>python -m backend.build_report</code> again.</div>')
        appr = "".join(f"<li>#{a['request_id']} {a['kind'].replace('_', ' ')} {money(a['amount'])} — {a['status']}"
                       f"{' by ' + esc(a['decided_by']) if a['decided_by'] else ''}</li>" for a in t["human_approvals"]) or "<li>None</li>"
        sections.append(f"""
<section>
  <div class="head"><h2>Ticket {t['id']} · {esc(t['requester'])}</h2>
    <span class="pill {'ok' if t['final_status'] == 'resolved' else ''}">{esc(t['final_status'])}</span></div>
  <p class="outcome">{esc(t['outcome'] or '')}</p>
  {img}
  <div class="meta"><div><b>Agents</b>: {', '.join(LABEL.get(a['agent'], a['agent']) for a in t['agents'])}</div>
    <div><b>Cash change</b>: {money(t['cash_change']) if t['cash_change'] else '$0.00'}</div></div>
  <ul>{appr}</ul>
</section>""")
    BOARD_HTML.write_text(f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Campus Customs — Resolved board</title>
<style>
 body{{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f4f6fa;color:#18202c}}
 header{{background:linear-gradient(120deg,#0d2340,#143259);color:#fff;padding:22px 32px}}
 header h1{{margin:0;font-size:22px}} header p{{margin:4px 0 0;color:#c6d5ea}}
 main{{max-width:1200px;margin:0 auto;padding:24px 32px 60px}}
 section{{background:#fff;border:1px solid #e3e7ee;border-radius:14px;padding:18px 20px;margin-bottom:22px;box-shadow:0 4px 16px rgba(16,24,40,.05)}}
 .head{{display:flex;align-items:center;justify-content:space-between}} h2{{margin:0;font-size:18px;color:#0d2340}}
 .pill{{padding:3px 12px;border-radius:999px;background:#eef2f7;font-weight:700;font-size:12px;text-transform:uppercase}}
 .pill.ok{{background:#e5f5ed;color:#12875a}} .outcome{{color:#3a4556}}
 img{{width:100%;border-radius:10px;border:1px solid #e3e7ee;margin:8px 0}}
 .missing{{padding:40px;text-align:center;border:2px dashed #d6dce5;border-radius:10px;color:#6b7686;margin:8px 0}}
 .meta{{display:flex;gap:28px;flex-wrap:wrap;color:#3a4556}} code{{background:#eef3fa;padding:1px 6px;border-radius:5px}}
</style></head><body>
<header><h1>Campus Customs — Resolved board</h1>
<p>Screenshots of the React dashboard after each ticket resolved · starting checking {money(cash['start'])} → ending {money(cash['end'])} (matches <code style="background:rgba(255,255,255,.15);color:#fff">cash_accounts</code>)</p></header>
<main>{''.join(sections)}</main></body></html>
""")

    print(f"Start {money(cash['start'])} - out {money(cash['total_out'])} = end {money(cash['end'])}  ✓ matches cash_accounts")
    print(f"Wrote {DESK.name}, {RESOLVED_JSON.name}, {BOARD_HTML.name}")
    if missing:
        print(f"WARNING: no run found after the last reset for tickets {missing}")
    if not_resolved:
        print(f"WARNING: not resolved yet: {not_resolved}")
    shots_missing = [tid for tid in TICKETS if not find_shot(tid)]
    if shots_missing:
        print(f"WARNING: screenshots missing for {shots_missing} (output/screenshots/ticket_<id>.png)")


if __name__ == "__main__":
    main()
