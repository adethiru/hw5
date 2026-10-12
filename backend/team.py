"""The Campus Customs multi-agent team (PydanticAI).

* Five agents (boss, inventory, accounting, facilities, customer_service),
  all on config.MODEL_NAME ("gpt-6-luna").
* Every agent reads/acts on the shop ONLY through the MCP server, via a
  role-filtered toolset (see backend/mcp_client.py).
* Full connectivity: every agent has `delegate_task(to_agent, task)` and may
  hand work to any other agent. Guardrails stop loops: no self-delegation,
  no delegating back up the current chain, max depth, max hand-offs per
  ticket, and one shared UsageLimits budget per ticket.
* Every agent-loop step (each node of PydanticAI's graph) is appended to
  output/audit_trail.json.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

from backend.agents import SPECS
from backend.audit import AuditTrail
from backend.config import (
    MAX_DELEGATION_DEPTH,
    MAX_DELEGATIONS_PER_TICKET,
    MODEL_NAME,
    PROMPTS_DIR,
    REQUEST_LIMIT_PER_TICKET,
    TOOL_CALLS_LIMIT_PER_TICKET,
    TOTAL_TOKENS_LIMIT_PER_TICKET,
)
from backend.llm import build_model, model_settings
from backend.mcp_client import ROLE_TOOLS, build_mcp_server, toolset_for
from backend.models import AgentName, TeamDeps, TicketDecision


def _usage_limits() -> UsageLimits:
    kwargs: dict[str, Any] = {
        "request_limit": REQUEST_LIMIT_PER_TICKET,
        "total_tokens_limit": TOTAL_TOKENS_LIMIT_PER_TICKET,
    }
    try:
        return UsageLimits(tool_calls_limit=TOOL_CALLS_LIMIT_PER_TICKET, **kwargs)
    except TypeError:  # older pydantic-ai without tool_calls_limit
        return UsageLimits(**kwargs)


def _usage_dict(usage: Any) -> dict:
    if usage is None:
        return {}
    out = {}
    for name in ("requests", "tool_calls", "input_tokens", "output_tokens",
                 "request_tokens", "response_tokens", "total_tokens"):
        v = getattr(usage, name, None)
        if isinstance(v, int):
            out[name] = v
    return out


def _part_summary(part: Any) -> dict:
    kind = getattr(part, "part_kind", type(part).__name__)
    d: dict[str, Any] = {"kind": kind}
    if kind == "tool-call":
        d["tool"] = part.tool_name
        d["args"] = part.args if isinstance(part.args, (dict, str)) else str(part.args)
        d["tool_call_id"] = getattr(part, "tool_call_id", None)
    elif kind == "tool-return":
        d["tool"] = part.tool_name
        content = part.content
        d["content"] = content if isinstance(content, str) else json.dumps(content, default=str)
        d["tool_call_id"] = getattr(part, "tool_call_id", None)
    elif kind == "retry-prompt":
        d["tool"] = getattr(part, "tool_name", None)
        d["content"] = str(part.content)
    elif kind in ("text", "user-prompt", "system-prompt", "thinking"):
        content = getattr(part, "content", "")
        d["content"] = content if isinstance(content, str) else str(content)
    return d


def _describe_node(node: Any) -> dict:
    """Turn one PydanticAI graph node into an audit record body."""
    if Agent.is_user_prompt_node(node):
        return {"node": "user_prompt", "prompt": str(node.user_prompt)}
    if Agent.is_model_request_node(node):
        return {"node": "model_request", "parts": [_part_summary(p) for p in node.request.parts]}
    if Agent.is_call_tools_node(node):
        resp = node.model_response
        return {
            "node": "model_response",
            "model_name": getattr(resp, "model_name", None),
            "parts": [_part_summary(p) for p in resp.parts],
            "tool_calls": [p.tool_name for p in resp.parts if getattr(p, "part_kind", "") == "tool-call"],
            "response_usage": _usage_dict(getattr(resp, "usage", None)),
        }
    if Agent.is_end_node(node):
        out = node.data.output
        return {"node": "end", "output": out.model_dump() if hasattr(out, "model_dump") else str(out)}
    return {"node": type(node).__name__}


def _team_roster(exclude: str) -> str:
    return "\n".join(
        f"- {s.name}: {s.description}" for s in SPECS.values() if s.name != exclude
    )


class CampusCustomsTeam:
    """Owns the MCP connection and the five agents. Use as an async context manager."""

    def __init__(self, audit: Optional[AuditTrail] = None):
        self.audit = audit or AuditTrail()
        self.mcp = build_mcp_server()
        shared_rules = (PROMPTS_DIR / "team_rules.md").read_text(encoding="utf-8")
        self.agents: dict[str, Agent] = {}
        for spec in SPECS.values():
            agent = Agent(
                build_model(),
                name=spec.name,
                instructions=spec.instructions()
                + "\n\n"
                + shared_rules
                + f"\n\n## Your teammates (use delegate_task)\n{_team_roster(spec.name)}",
                deps_type=TeamDeps,
                output_type=spec.output_type,
                toolsets=[toolset_for(self.mcp, spec.name)],
                model_settings=model_settings(),
                retries=2,
            )
            agent.tool(self._make_delegate_tool())
            self.agents[spec.name] = agent

    # ------------------------------------------------------------------ #
    async def __aenter__(self) -> "CampusCustomsTeam":
        await self.mcp.__aenter__()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.mcp.__aexit__(*exc)

    # ------------------------------------------------------------------ #
    # Delegation tool (full connectivity)
    # ------------------------------------------------------------------ #
    def _make_delegate_tool(self):
        team = self

        async def delegate_task(ctx: RunContext[TeamDeps], to_agent: AgentName, task: str) -> str:
            """Hand a focused sub-task to another Campus Customs agent and get its report back.

            Any agent may delegate to any other agent. Write `task` as a complete,
            self-contained instruction: the ticket id, the SKU/size/qty or
            lease/invoice id, the facts you already have, and exactly what you
            need back. The teammate returns a JSON report.

            Args:
                to_agent: boss | inventory | accounting | facilities | customer_service
                task: The self-contained request for that agent.
            """
            deps = ctx.deps
            refusal = None
            if to_agent == deps.agent:
                refusal = "You cannot delegate to yourself."
            elif to_agent in deps.chain:
                refusal = (f"{to_agent} is already working upstream in this chain {deps.chain}. "
                           "Return your findings instead of delegating back.")
            elif deps.depth + 1 > MAX_DELEGATION_DEPTH:
                refusal = f"Max delegation depth {MAX_DELEGATION_DEPTH} reached; finish with what you have."
            elif deps.budget.used >= MAX_DELEGATIONS_PER_TICKET:
                refusal = f"Delegation budget ({MAX_DELEGATIONS_PER_TICKET} per ticket) is used up."
            if refusal:
                team.audit.append({
                    "run_id": deps.run_id, "ticket_id": deps.ticket_id, "agent": deps.agent,
                    "event": "delegation_refused", "to_agent": to_agent, "task": task,
                    "reason": refusal, "chain": deps.chain, "depth": deps.depth,
                })
                return json.dumps({"ok": False, "error": refusal})

            deps.budget.used += 1
            team.audit.append({
                "run_id": deps.run_id, "ticket_id": deps.ticket_id, "agent": deps.agent,
                "event": "delegation", "to_agent": to_agent, "task": task,
                "chain": [*deps.chain, to_agent], "depth": deps.depth + 1,
                "delegations_used": deps.budget.used, "parent_step_id": deps.parent_step_id,
            })
            child = deps.child(to_agent, parent_step_id=deps.parent_step_id)
            try:
                output = await team.run_agent_loop(to_agent, task, child, usage=ctx.usage)
            except UsageLimitExceeded:
                raise  # the ticket-level budget is shared; stop the whole ticket
            except Exception as e:  # report failure to the caller instead of crashing
                team.audit.append({
                    "run_id": deps.run_id, "ticket_id": deps.ticket_id, "agent": to_agent,
                    "event": "agent_error", "error": repr(e), "chain": child.chain,
                })
                return json.dumps({"ok": False, "error": f"{to_agent} failed: {e}"})
            return json.dumps({"ok": True, "from": to_agent, "report": output.model_dump()})

        return delegate_task

    # ------------------------------------------------------------------ #
    # The agent loop (one PydanticAI run, every node audited)
    # ------------------------------------------------------------------ #
    async def run_agent_loop(self, name: str, prompt: str, deps: TeamDeps, usage=None):
        agent = self.agents[name]
        base = {"run_id": deps.run_id, "ticket_id": deps.ticket_id, "agent": name,
                "model": MODEL_NAME, "depth": deps.depth, "chain": deps.chain}
        self.audit.append({**base, "event": "agent_start", "prompt": prompt,
                           "mcp_tools_allowed": sorted(ROLE_TOOLS[name]) + ["delegate_task"]})
        step = 0
        async with agent.iter(prompt, deps=deps, usage=usage, usage_limits=_usage_limits()) as run:
            async for node in run:
                step += 1
                step_id = self.audit.append({**base, "event": "loop_step", "step": step,
                                             **_describe_node(node),
                                             "cumulative_usage": _usage_dict(run.usage())})
                deps.parent_step_id = step_id  # delegations made in this step point here
            result = run.result
        self.audit.append({**base, "event": "agent_end", "steps": step,
                           "output": result.output.model_dump(),
                           "cumulative_usage": _usage_dict(run.usage())})
        return result.output

    # ------------------------------------------------------------------ #
    # Ticket entry points
    # ------------------------------------------------------------------ #
    async def list_open_ticket_ids(self) -> list[int]:
        res = await self.mcp.direct_call_tool("list_tickets", {"status": "open"})
        if isinstance(res, str):
            res = json.loads(res)
        return [t["id"] for t in res["tickets"]]

    async def run_ticket(self, ticket_id: int, run_id: Optional[str] = None) -> Optional[TicketDecision]:
        run_id = run_id or uuid.uuid4().hex[:10]
        deps = TeamDeps(run_id=run_id, ticket_id=ticket_id, agent="boss", audit=self.audit, chain=["boss"])
        prompt = (
            f"Handle ticket {ticket_id}. Start by calling get_ticket({ticket_id}). "
            "Follow your playbook, delegate to the right teammates, make sure every needed "
            "approval request and customer draft is filed, update the ticket status, and "
            "return your TicketDecision."
        )
        self.audit.append({"run_id": run_id, "ticket_id": ticket_id, "agent": "boss",
                           "event": "ticket_start", "model": MODEL_NAME})
        try:
            decision = await self.run_agent_loop("boss", prompt, deps)
        except UsageLimitExceeded as e:
            self.audit.append({"run_id": run_id, "ticket_id": ticket_id, "agent": "boss",
                               "event": "ticket_stopped_usage_limit", "error": str(e)})
            return None
        except Exception as e:
            self.audit.append({"run_id": run_id, "ticket_id": ticket_id, "agent": "boss",
                               "event": "ticket_error", "error": repr(e)})
            raise
        self.audit.append({"run_id": run_id, "ticket_id": ticket_id, "agent": "boss",
                           "event": "ticket_end", "decision": decision.model_dump(),
                           "delegations_used": deps.budget.used})
        return decision

    async def run_open_tickets(self) -> dict[int, Optional[TicketDecision]]:
        """Run every open ticket, one at a time (they compete for the same cash)."""
        run_id = uuid.uuid4().hex[:10]
        results = {}
        for tid in await self.list_open_ticket_ids():
            results[tid] = await self.run_ticket(tid, run_id=f"{run_id}-t{tid}")
        return results
