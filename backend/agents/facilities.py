"""Facilities agent - Handles the shop space: leases, rent amounts and due dates, landlord notices."""

from backend.agents.base import AgentSpec
from backend.models import SpecialistReport

SPEC = AgentSpec(
    name="facilities",
    title="Facilities",
    description="Handles the shop space: leases, rent amounts and due dates, landlord notices.",
    prompt_file="facilities.md",
    output_type=SpecialistReport,
)
