"""Command-line runner for the agent team.

    python -m backend.run_team --ticket 101          # one ticket, current DB state
    python -m backend.run_team --all                 # RESETS the DB, then all open tickets
    python -m backend.run_team --all --keep-db       # all open tickets without reset

Agents never pay anything: they file approval requests. A human approves on
the dashboard (later problem).
"""

from __future__ import annotations

import argparse
import asyncio
import json

from backend.reset_db import reset_working_db
from backend.team import CampusCustomsTeam


async def _main(args) -> None:
    if args.all and not args.keep_db:
        reset_working_db(actor="system")  # rule: reset to original values before a full run
    async with CampusCustomsTeam() as team:
        if args.all:
            results = await team.run_open_tickets()
        else:
            results = {t: await team.run_ticket(t) for t in args.ticket}
    for tid, decision in results.items():
        print(f"\n=== Ticket {tid} ===")
        print(json.dumps(decision.model_dump() if decision else {"stopped": "usage limit"}, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(description="Run the Campus Customs agent team.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--ticket", type=int, action="append", help="Ticket id (repeatable).")
    g.add_argument("--all", action="store_true", help="Reset DB, then run every open ticket.")
    p.add_argument("--keep-db", action="store_true", help="With --all: skip the reset.")
    asyncio.run(_main(p.parse_args()))


if __name__ == "__main__":
    main()
