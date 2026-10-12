"""Data types shared by the Campus Customs agent team."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from backend.audit import AuditTrail

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
TicketStatus = Literal["open", "in_progress", "awaiting_approval", "blocked", "resolved"]


# --------------------------------------------------------------------------- #
# Structured outputs (what each agent must return at the end of its loop)
# --------------------------------------------------------------------------- #
class Fact(BaseModel):
    """A fact the agent relied on, tied to the MCP tool that returned it."""

    statement: str = Field(description="One fact, with the exact number/date from the tool.")
    source_tool: str = Field(description="MCP tool name that returned this fact.")


class SpecialistReport(BaseModel):
    """Returned by Inventory, Accounting, Facilities and Customer Service."""

    agent: AgentName
    ticket_id: Optional[int] = None
    summary: str = Field(description="2-4 sentences: what was checked and what it means.")
    facts: list[Fact] = Field(default_factory=list)
    recommendation: str = Field(description="What this agent recommends the Boss do next.")
    approval_request_ids: list[int] = Field(
        default_factory=list, description="IDs of approval requests this agent filed (pending human)."
    )
    draft_ids: list[int] = Field(default_factory=list, description="IDs of customer drafts saved.")
    blockers: list[str] = Field(default_factory=list, description="Anything stopping progress.")
    needs_human: bool = Field(description="True if a human must approve or decide something.")


class TicketDecision(BaseModel):
    """Returned by the Boss once per ticket - the final call."""

    ticket_id: int
    ticket_type: str
    assigned_agents: list[AgentName] = Field(description="Specialists the Boss delegated to.")
    decision: str = Field(description="The Boss's final call in plain English.")
    facts: list[Fact] = Field(default_factory=list)
    approval_request_ids: list[int] = Field(default_factory=list)
    draft_ids: list[int] = Field(default_factory=list)
    final_status: TicketStatus
    human_actions_needed: list[str] = Field(
        default_factory=list, description="Exactly what the human must approve/decide on the dashboard."
    )
    risks: list[str] = Field(default_factory=list, description="Cash, timing or policy risks.")


# --------------------------------------------------------------------------- #
# Run-time dependencies passed to every agent / tool via RunContext.deps
# --------------------------------------------------------------------------- #
@dataclass
class DelegationBudget:
    """Shared, mutable counter for one ticket's whole delegation tree."""

    used: int = 0


@dataclass
class TeamDeps:
    run_id: str
    ticket_id: Optional[int]
    agent: AgentName
    audit: "AuditTrail"
    depth: int = 0
    chain: list[str] = field(default_factory=list)  # e.g. ["boss", "inventory"]
    budget: DelegationBudget = field(default_factory=DelegationBudget)
    parent_step_id: Optional[str] = None

    def child(self, agent: AgentName, parent_step_id: Optional[str]) -> "TeamDeps":
        return TeamDeps(
            run_id=self.run_id,
            ticket_id=self.ticket_id,
            agent=agent,
            audit=self.audit,
            depth=self.depth + 1,
            chain=[*self.chain, agent],
            budget=self.budget,
            parent_step_id=parent_step_id,
        )
