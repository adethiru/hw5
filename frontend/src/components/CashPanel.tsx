import type { Approval, Cash } from "../types";
import { money } from "../format";
import { IconWallet } from "./Icons";

/** Balance history reconstructed from executed payments (cash only goes out). */
export default function CashPanel({ cash, approvals }: { cash: Cash | null; approvals: Approval[] }) {
  if (!cash) return null;
  const paid = approvals
    .filter((a) => (a.kind === "payment" || a.kind === "purchase_order") && a.status === "executed")
    .sort((a, b) => (a.executed_at ?? "").localeCompare(b.executed_at ?? ""));
  const start = cash.balance + paid.reduce((n, a) => n + a.amount, 0);
  const points = [start];
  paid.forEach((a) => points.push(points[points.length - 1] - a.amount));

  const W = 280, H = 64, pad = 6;
  const max = Math.max(...points, 1);
  const xs = (i: number) => pad + (points.length === 1 ? (W - 2 * pad) / 2 : (i * (W - 2 * pad)) / (points.length - 1));
  const ys = (v: number) => H - pad - (v / max) * (H - 2 * pad);
  const path = points.map((v, i) => `${i ? "L" : "M"}${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(" ");
  const area = `${path} L${xs(points.length - 1).toFixed(1)},${H - pad} L${xs(0).toFixed(1)},${H - pad} Z`;
  const pct = start ? (cash.balance / start) * 100 : 0;

  return (
    <div className="panel cash-panel">
      <div className="panel-head">
        <h2><IconWallet size={16} /> Cash</h2>
        <span className="muted small">checking · {cash.as_of}</span>
      </div>
      <div className="cash-big">{money(cash.balance)}</div>
      <div className="cash-bar"><div style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} /></div>
      <div className="muted small">{pct.toFixed(0)}% of opening {money(start)} · no revenue modeled, cash only goes out</div>

      <svg className="spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="cashfill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#1f5fa8" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#1f5fa8" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#cashfill)" />
        <path d={path} fill="none" stroke="#1f5fa8" strokeWidth="2" />
        {points.map((v, i) => <circle key={i} cx={xs(i)} cy={ys(v)} r="3" fill="#fff" stroke="#1f5fa8" strokeWidth="2" />)}
      </svg>

      <div className="ledger">
        <div className="ledger-row head"><span>Opening</span><span className="mono">{money(start)}</span></div>
        {paid.map((a) => (
          <div key={a.id} className="ledger-row">
            <span>
              {a.kind === "purchase_order"
                ? `PO · ${String((a.details as { qty?: number }).qty)}× ${String((a.details as { sku?: string }).sku)} (${String((a.details as { vendor_name?: string }).vendor_name)})`
                : String((a.details as { payee?: string }).payee ?? a.target_type)}{" "}
              <span className="muted">· by {a.decided_by}</span>
            </span>
            <span className="mono neg">−{money(a.amount)}</span>
          </div>
        ))}
        <div className="ledger-row total"><span>Now</span><span className="mono">{money(cash.balance)}</span></div>
        <div className="ledger-row sub"><span>Open invoices owed</span><span className="mono">{money(cash.open_invoice_total)}</span></div>
        <div className="ledger-row sub"><span>Queued for approval</span><span className="mono">{money(cash.pending_payment_requests_total)}</span></div>
        <div className={`ledger-row sub ${cash.cash_after_pending_payments < 0 ? "neg" : ""}`}>
          <span>If all queued are paid</span><span className="mono">{money(cash.cash_after_pending_payments)}</span>
        </div>
      </div>
    </div>
  );
}
