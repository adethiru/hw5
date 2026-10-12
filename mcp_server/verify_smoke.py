"""Check output/mcp_smoke.json against data/campus_customs_new.db.

Usage:  .venv/bin/python mcp_server/verify_smoke.py
Reads the DB directly (read-only) and confirms the key values each tool
reported in the smoke file match the database.
"""

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "campus_customs_new.db"
SMOKE = ROOT / "output" / "mcp_smoke.json"


def main() -> int:
    smoke = json.loads(SMOKE.read_text())
    tests = {t["tool"]: t for t in smoke["tests"]}
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    q = lambda sql, *a: conn.execute(sql, a).fetchone()
    checks = []

    out = tests["check_inventory_stock"]["tool_output"]
    item = out["items"][0]
    db_qty, db_loc = q("SELECT qty, location FROM inventory WHERE sku=? AND size=?",
                       item["sku"], item["size"])
    checks.append(("inventory qty", item["qty"], db_qty))
    checks.append(("inventory location", item["location"], db_loc))

    out = tests["check_vendor_status"]["tool_output"]
    v = out["vendors"][0]
    db_v = q("SELECT name, lead_days FROM vendors WHERE id=?", v["vendor_id"])
    checks.append(("vendor name", v["name"], db_v[0]))
    checks.append(("vendor lead_days", v["lead_days"], db_v[1]))
    for inv in v["open_invoices"]:
        db_inv = q("SELECT amount, due_date, status FROM invoices WHERE id=?", inv["invoice_id"])
        checks.append((f"invoice {inv['invoice_id']} amount", inv["amount"], db_inv[0]))
        checks.append((f"invoice {inv['invoice_id']} due_date", inv["due_date"], db_inv[1]))
        checks.append((f"invoice {inv['invoice_id']} status", "open", db_inv[2]))

    out = tests["get_lease_rent_status"]["tool_output"]
    db_l = q("SELECT monthly_rent, next_due, landlord FROM leases WHERE id=?", out["lease_id"])
    checks.append(("lease rent", out["monthly_rent"], db_l[0]))
    checks.append(("lease next_due", out["next_due"], db_l[1]))
    checks.append(("lease landlord", out["landlord"], db_l[2]))
    for a in out["cash_accounts"]:
        db_b = q("SELECT balance FROM cash_accounts WHERE name=?", a["account"])[0]
        checks.append((f"cash {a['account']}", a["balance"], db_b))

    ok = True
    for name, got, want in checks:
        good = got == want
        ok &= good
        print(f"{'PASS' if good else 'FAIL'}  {name}: smoke={got!r} db={want!r}")
    print("\nALL MATCH" if ok else "\nMISMATCH FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
