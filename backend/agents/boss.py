"""Boss agent - Reads each ticket, decides who works on it, coordinates the team and makes the final call."""

from backend.agents.base import AgentSpec
from backend.models import TicketDecision

SPEC = AgentSpec(
    name="boss",
    title="Boss",
    description="Reads each ticket, decides who works on it, coordinates the team and makes the final call.",
    prompt_file="boss.md",
    output_type=TicketDecision,
)
