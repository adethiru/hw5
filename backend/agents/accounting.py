"""Accounting agent - Watches cash and invoices, checks margins, and files payment / purchase-order / price-override requests for human approval."""

from backend.agents.base import AgentSpec
from backend.models import SpecialistReport

SPEC = AgentSpec(
    name="accounting",
    title="Accounting",
    description="Watches cash and invoices, checks margins, and files payment / purchase-order / price-override requests for human approval.",
    prompt_file="accounting.md",
    output_type=SpecialistReport,
)
