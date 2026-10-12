"""Customer Service agent - Drafts honest messages to customers (saved as drafts on the board, never sent)."""

from backend.agents.base import AgentSpec
from backend.models import SpecialistReport

SPEC = AgentSpec(
    name="customer_service",
    title="Customer Service",
    description="Drafts honest messages to customers (saved as drafts on the board, never sent).",
    prompt_file="customer_service.md",
    output_type=SpecialistReport,
)
