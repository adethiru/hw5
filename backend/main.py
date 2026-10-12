"""Campus Customs FastAPI backend.

Start from the backend/ folder:
    uvicorn main:app --reload --port 8000

All shop reads/writes go through the Campus Customs MCP server (one stdio
connection held for the app's lifetime) - the same tools the agents use. The
human-only MCP tools (approve / pay / place PO) are called ONLY from the
approve route below, after a human clicks Approve on the dashboard.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Allow `uvicorn main:app` from inside backend/ (package imports need the project root).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from backend.audit import AuditTrail  # noqa: E402
from backend.config import AUDIT_TRAIL, MODEL_NAME, WORKING_DB  # noqa: E402
from backend.reset_db import reset_working_db  # noqa: E402
from backend.team import CampusCustomsTeam  # noqa: E402

AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service"}


# --------------------------------------------------------------------------- #
# App state: one team (+ its MCP connection), one run at a time
# --------------------------------------------------------------------------- #
class State:
    team: Optional[CampusCustomsTeam] = None
    audit: AuditTrail = AuditTrail()
    run_lock = asyncio.Lock()
    runs: dict[str, dict] = {}


state = State()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not WORKING_DB.exists():
        reset_working_db(actor="system")
    state.team = CampusCustomsTeam(audit=state.audit)
    async with state.team:
        yield
    state.team = None


app = FastAPI(title="Campus Customs Backend", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def mcp(tool: str, args: Optional[dict] = None) -> Any:
    """Call a Campus Customs MCP tool and return its parsed result."""
    if state.team is None:
        raise HTTPException(503, "Backend is starting up.")
    try:
        res = await state.team.mcp.direct_call_tool(tool, args or {})
    except Exception as e:
        raise HTTPException(502, f"MCP tool {tool} failed: {e}")
    if isinstance(res, str):
        try:
            res = json.loads(res)
        except json.JSONDecodeError:
            pass
    if isinstance(res, dict) and set(res) == {"result"}:  # FastMCP wrapper
        res = res["result"]
    return res


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class Decision(BaseModel):
    approved_by: str = Field(..., min_length=1, description="Name of the human approver.")
    note: str = ""


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/api/health")
async def health():
    return {"ok": True, "model": MODEL_NAME, "db": WORKING_DB.name,
            "run_in_progress": state.run_lock.locked()}


# 1. Tickets ------------------------------------------------------------------
@app.get("/api/tickets")
async def get_tickets():
    """All tickets with an open/resolved flag (status != 'resolved' counts as open)."""
    data = await mcp("list_tickets", {"status": "all"})
    tickets = []
    for t in data["tickets"]:
        tickets.append({**t, "is_resolved": t["status"] == "resolved",
                        "state": "resolved" if t["status"] == "resolved" else "open"})
    return {"shop_today": data["shop_today"], "tickets": tickets}


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: int):
    data = await mcp("get_ticket", {"ticket_id": ticket_id})
    if not data.get("found"):
        raise HTTPException(404, data.get("error", "Ticket not found"))
    return data


# 2. Run the agent team on one ticket ----------------------------------------
async def _close_ticket(ticket_id: int, run_id: str, decision) -> None:
    """When a run finishes and the Boss did not report 'blocked', make sure the
    ticket shows as resolved on the board (pending human approvals stay listed)."""
    t = await mcp("get_ticket", {"ticket_id": ticket_id})
    if t.get("found") and t["ticket"]["status"] != "resolved":
        pending = ", ".join(f"#{i}" for i in decision.approval_request_ids) or "none"
        res = await mcp("update_ticket", {
            "ticket_id": ticket_id, "status": "resolved", "updated_by": "system",
            "note": f"Agent run {run_id} finished. Pending human approvals: {pending}."})
        state.audit.append({"run_id": run_id, "ticket_id": ticket_id, "agent": "system",
                            "event": "ticket_marked_resolved", "result": res})


async def _run_ticket_job(run_id: str, ticket_id: int):
    rec = state.runs[run_id]
    try:
        async with state.run_lock:
            rec["status"] = "running"
            decision = await state.team.run_ticket(ticket_id, run_id=run_id)
            if decision is not None and decision.final_status != "blocked":
                await _close_ticket(ticket_id, run_id, decision)
        rec["decision"] = decision.model_dump() if decision else None
        rec["status"] = "done" if decision else "stopped_usage_limit"
    except Exception as e:
        rec["status"] = "error"
        rec["error"] = repr(e)
    rec["finished_at"] = _now()


@app.post("/api/tickets/{ticket_id}/run")
async def run_ticket(ticket_id: int, wait: bool = Query(False, description="Block until done")):
    """Start the agent team on a ticket. Returns a run_id; poll /api/runs/{run_id} or /api/events."""
    t = await mcp("get_ticket", {"ticket_id": ticket_id})
    if not t.get("found"):
        raise HTTPException(404, t.get("error", "Ticket not found"))
    if state.run_lock.locked():
        raise HTTPException(409, "Another ticket run is in progress; runs are one at a time.")
    run_id = uuid.uuid4().hex[:10]
    state.runs[run_id] = {"run_id": run_id, "ticket_id": ticket_id, "status": "queued",
                          "started_at": _now(), "model": MODEL_NAME}
    task = asyncio.create_task(_run_ticket_job(run_id, ticket_id))
    if wait:
        await task
    return state.runs[run_id]


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    if run_id not in state.runs:
        raise HTTPException(404, "Unknown run_id")
    return state.runs[run_id]


@app.get("/api/runs")
async def list_runs():
    return {"runs": list(state.runs.values())[::-1]}


# 3. Recent agent events -------------------------------------------------------
def _summarize(i: int, r: dict) -> Optional[dict]:
    """Compress one audit record to what the board shows: who said what, which tools."""
    base = {"index": i, "logged_at": r.get("logged_at"), "run_id": r.get("run_id"),
            "ticket_id": r.get("ticket_id"), "agent": r.get("agent"), "event": r.get("event"),
            "depth": r.get("depth"), "chain": r.get("chain")}
    ev = r.get("event")
    if ev == "loop_step":
        node = r.get("node")
        parts = r.get("parts") or []
        if node == "model_response":
            return {**base, "kind": "said", "step": r.get("step"), "model_name": r.get("model_name"),
                    "text": "\n".join(p.get("content", "") for p in parts if p.get("kind") == "text").strip(),
                    "tool_calls": [{"tool": p.get("tool"), "args": p.get("args")}
                                   for p in parts if p.get("kind") == "tool-call"],
                    "usage": r.get("cumulative_usage")}
        if node == "model_request":
            returns = [{"tool": p.get("tool"), "result": (p.get("content") or "")[:600]}
                       for p in parts if p.get("kind") in ("tool-return", "retry-prompt")]
            if not returns:
                return None  # initial prompt request - shown by agent_start
            return {**base, "kind": "tool_results", "step": r.get("step"), "tool_results": returns}
        if node == "end":
            return {**base, "kind": "final", "step": r.get("step"), "output": r.get("output")}
        return None
    if ev == "agent_start":
        return {**base, "kind": "start", "text": r.get("prompt")}
    if ev in ("delegation", "delegation_refused"):
        return {**base, "kind": ev, "to_agent": r.get("to_agent"), "text": r.get("task"),
                "reason": r.get("reason")}
    if ev in ("ticket_start", "ticket_end", "agent_end", "agent_error", "ticket_error",
              "ticket_stopped_usage_limit", "ticket_marked_resolved", "human_decision", "human_payment", "human_purchase_order",
              "db_reset"):
        keep = {k: r[k] for k in ("decision", "error", "result", "request_id", "approved_by", "starting_checking_balance",
                                  "output", "cumulative_usage") if k in r}
        return {**base, "kind": ev, **keep}
    return None


@app.get("/api/events")
async def get_events(
    limit: int = Query(100, ge=1, le=1000),
    after: int = Query(-1, description="Only events with index > after (for incremental refresh)."),
    ticket_id: Optional[int] = None,
    run_id: Optional[str] = None,
    agent: Optional[str] = None,
):
    """Recent agent events from output/audit_trail.json (newest last)."""
    try:
        records = json.loads(AUDIT_TRAIL.read_text() or "[]") if AUDIT_TRAIL.exists() else []
    except json.JSONDecodeError:
        records = []
    out = []
    for i, r in enumerate(records):
        if i <= after:
            continue
        if ticket_id is not None and r.get("ticket_id") != ticket_id:
            continue
        if run_id and not str(r.get("run_id", "")).startswith(run_id):
            continue
        if agent and r.get("agent") != agent:
            continue
        s = _summarize(i, r)
        if s:
            out.append(s)
    return {"total_records": len(records), "next_after": len(records) - 1, "events": out[-limit:]}


# 4. Approvals: the human clicks Approve -> this route moves the money --------
@app.get("/api/approvals")
async def get_approvals(status: str = "all", ticket_id: Optional[int] = None):
    args: dict = {"status": status}
    if ticket_id is not None:
        args["ticket_id"] = ticket_id
    return await mcp("list_approval_requests", args)


@app.get("/api/drafts")
async def get_drafts(ticket_id: Optional[int] = None):
    return await mcp("list_customer_drafts", {} if ticket_id is None else {"ticket_id": ticket_id})


def _human_name(name: str) -> str:
    n = name.strip()
    if not n or n.lower() in AGENT_NAMES or "agent" in n.lower():
        raise HTTPException(400, "approved_by must be a human name, not an agent.")
    return n


@app.post("/api/approvals/{request_id}/approve")
async def approve(request_id: int, body: Decision):
    """Human approval. Payments: approve + pay (debits cash, writes payments, marks invoice
    paid / advances rent). Purchase orders: approve + place (refused while the vendor has an
    open invoice). Price overrides: approve only. Refuses if cash would go negative."""
    who = _human_name(body.approved_by)
    if state.run_lock.locked():
        raise HTTPException(409, "Wait for the running ticket to finish before approving.")
    reqs = await mcp("list_approval_requests", {"status": "all"})
    req = next((r for r in reqs["approval_requests"] if r["id"] == request_id), None)
    if req is None:
        raise HTTPException(404, f"No approval request {request_id}.")

    if req["status"] == "pending":
        d = await mcp("decide_approval_request",
                      {"request_id": request_id, "decision": "approved", "decided_by": who, "note": body.note})
        if not d.get("ok"):
            raise HTTPException(409, d.get("error"))
        state.audit.append({"agent": "human", "event": "human_decision", "ticket_id": req["ticket_id"],
                            "request_id": request_id, "approved_by": who, "result": d})
    elif req["status"] != "approved":
        raise HTTPException(409, f"Request {request_id} is already '{req['status']}'.")

    if req["kind"] == "payment":
        res = await mcp("execute_approved_payment", {"request_id": request_id})
        state.audit.append({"agent": "human", "event": "human_payment", "ticket_id": req["ticket_id"],
                            "request_id": request_id, "approved_by": who, "result": res})
        if not res.get("ok"):
            raise HTTPException(409, res.get("error"))  # e.g. not enough cash - nothing changed
    elif req["kind"] == "purchase_order":
        res = await mcp("place_approved_purchase_order", {"request_id": request_id})
        state.audit.append({"agent": "human", "event": "human_purchase_order", "ticket_id": req["ticket_id"],
                            "request_id": request_id, "approved_by": who, "result": res})
        if not res.get("ok"):
            raise HTTPException(409, res.get("error"))
    else:
        res = {"ok": True, "note": "Price override approved. No cash moves."}

    cash = await get_cash()
    return {"request_id": request_id, "kind": req["kind"], "approved_by": who, "result": res, "cash": cash}


@app.post("/api/approvals/{request_id}/reject")
async def reject(request_id: int, body: Decision):
    who = _human_name(body.approved_by)
    d = await mcp("decide_approval_request",
                  {"request_id": request_id, "decision": "rejected", "decided_by": who, "note": body.note})
    if not d.get("ok"):
        raise HTTPException(409, d.get("error"))
    state.audit.append({"agent": "human", "event": "human_decision", "request_id": request_id,
                        "approved_by": who, "result": d})
    return d


# 5. Cash ------------------------------------------------------------------------
@app.get("/api/cash")
async def get_cash():
    """Current checking balance from cash_accounts (plus what's owed and queued)."""
    pos = await mcp("get_cash_position")
    checking = next((a for a in pos["cash_accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(404, "No checking account.")
    return {"account": "checking", "balance": checking["balance"], "as_of": checking["date"],
            "shop_today": pos["shop_today"], "open_invoice_total": pos["open_invoice_total"],
            "pending_payment_requests_total": pos["pending_payment_requests_total"],
            "cash_after_pending_payments": pos["cash_after_pending_payments"]}


@app.get("/api/payments")
async def get_payments():
    """Executed payments (from approval requests marked executed)."""
    return await mcp("list_approval_requests", {"status": "executed"})


# 6. Reset ---------------------------------------------------------------------
@app.post("/api/reset")
async def reset():
    """Copy data/campus_customs.db over data/campus_customs_new.db. The audit trail is kept."""
    if state.run_lock.locked():
        raise HTTPException(409, "A ticket run is in progress; reset after it finishes.")
    reset_working_db(actor="human")  # appends a db_reset record with the starting balance
    state.runs.clear()
    cash = await get_cash()
    tickets = await get_tickets()
    return {"ok": True, "cash": cash, "tickets": [{"id": t["id"], "status": t["status"]} for t in tickets["tickets"]]}
