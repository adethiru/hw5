"""The five Campus Customs agent roles."""

from backend.agents import accounting, boss, customer_service, facilities, inventory

SPECS = {s.name: s for s in (boss.SPEC, inventory.SPEC, accounting.SPEC, facilities.SPEC, customer_service.SPEC)}

__all__ = ["SPECS"]
