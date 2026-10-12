"""Inventory agent - Checks stock by SKU and size, computes shortfalls, and finds which vendor can restock and when."""

from backend.agents.base import AgentSpec
from backend.models import SpecialistReport

SPEC = AgentSpec(
    name="inventory",
    title="Inventory",
    description="Checks stock by SKU and size, computes shortfalls, and finds which vendor can restock and when.",
    prompt_file="inventory.md",
    output_type=SpecialistReport,
)
