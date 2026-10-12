"""Reset the working DB from the untouched original.

    python -m backend.reset_db

Copies data/campus_customs.db -> data/campus_customs_new.db. The original is
only read. The audit trail is NOT wiped - a `db_reset` record (with the
starting checking balance) is appended so reports know where a clean run began.
"""

from __future__ import annotations

import shutil
import sqlite3

from backend.audit import AuditTrail
from backend.config import ORIGINAL_DB, WORKING_DB


def reset_working_db(actor: str = "human") -> float:
    if not ORIGINAL_DB.exists():
        raise FileNotFoundError(f"Original DB missing: {ORIGINAL_DB}")
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    with sqlite3.connect(WORKING_DB) as conn:
        bal = conn.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
    AuditTrail().append({"agent": actor, "event": "db_reset",
                         "result": f"{WORKING_DB.name} restored from {ORIGINAL_DB.name}",
                         "starting_checking_balance": bal})
    print(f"Reset {WORKING_DB.name} from {ORIGINAL_DB.name}. Starting checking balance: ${bal:,.2f}")
    return bal


if __name__ == "__main__":
    reset_working_db()
