import type { Approval, Cash } from "../types";
import { money, titleCase } from "../format";
import { metaFor } from "../agents";
import { IconCheck, IconShield, IconX } from "./Icons";

interface Props {
  approvals: Approval[];
  cash: Cash | null;
  approver: string;
  setApprover: (s: string) => void;
  busyId: number | null;
  disabled: boolean;
  selectedTicketId: number | null;
  onApprove: (a: Approval) => void;
  onReject: (a: Approval) => void;
}

const KIND: Record<string, { label: string; verb: string }> = {
  payment: { label: "Payment", verb: "Approve & pay" },
  purchase_order: { label: "Purchase order", verb: "Approve & order" },
  price_override: { label: "Price override", verb: "Approve price" },
};

function detailLine(a: Approval): string {
  const d = a.details as Record<string, string | number | number[] | undefined>;
  if (a.kind === "payment") {
    const due = d.days_overdue ? `${d.days_overdue} days overdue` : d.days_until_due != null ? `due in ${d.days_until_due} days` : "";
    return [d.payee, d.description ?? d.space_name, due].filter(Boolean).join(" · ");
  }
  if (a.kind === "purchase_order") {
    return `${d.qty} × ${d.sku} ${d.size} from ${d.vendor_name} · ${d.lead_days} lead days`;
  }
  return `${d.qty} × ${d.sku} at ${money(Number(d.proposed_unit_price))} (${d.discount_pct}% off · ${d.margin_pct}% margin)`;
}

export default function ApprovalsPanel({ approvals, cash, approver, setApprover, busyId, disabled, selectedTicketId, onApprove, onReject }: Props) {
  const done = (a: Approval) =>
    a.status === "executed" || a.status === "rejected" || (a.kind === "price_override" && a.status === "approved");
  const queue = approvals.filter((a) => !done(a));
  const history = approvals.filter(done).slice().reverse();
  // show the selected ticket's requests first
  queue.sort((x, y) => Number(y.ticket_id === selectedTicketId) - Number(x.ticket_id === selectedTicketId) || x.id - y.id);

  return (
    <div className="panel approvals">
      <div className="panel-head">
        <h2><IconShield size={16} /> Approvals</h2>
        <span className={`count-badge ${queue.length ? "hot" : ""}`}>{queue.length}</span>
      </div>
      <p className="muted small">Agents only <i>prepare</i> these. Nothing is paid or ordered until you approve.</p>

      <label className="approver">
        <span>Approving as</span>
        <input value={approver} onChange={(e) => setApprover(e.target.value)} placeholder="Your name" />
      </label>

      <div className="approval-list">
        {queue.length === 0 && <div className="empty small">Nothing waiting for you.</div>}
        {queue.map((a) => {
          const k = KIND[a.kind];
          const after = cash ? cash.balance - a.amount : null;
          const moves = a.kind === "payment" || a.kind === "purchase_order";
          const short = moves && cash != null && a.amount > cash.balance;
          const blocked = a.kind === "purchase_order" && Array.isArray((a.details as { vendor_blocked_by_open_invoices?: number[] }).vendor_blocked_by_open_invoices)
            && ((a.details as { vendor_blocked_by_open_invoices: number[] }).vendor_blocked_by_open_invoices.length > 0);
          const by = metaFor(a.requested_by);
          return (
            <div key={a.id} className={`approval k-${a.kind} ${a.ticket_id === selectedTicketId ? "focus" : ""}`}>
              <div className="approval-top">
                <span className={`kind-tag k-${a.kind}`}>{k.label}</span>
                <span className="muted small">#{a.id} · ticket {a.ticket_id ?? "—"}</span>
              </div>
              <div className="approval-amount">{a.kind === "price_override" ? money(Number((a.details as { proposed_unit_price?: number }).proposed_unit_price)) + " / unit" : money(a.amount)}</div>
              <div className="approval-detail">{detailLine(a)}</div>
              {moves && cash && (
                <div className={`impact ${short ? "bad" : ""}`}>
                  Checking {money(cash.balance)} → <b>{short ? "refused (would go negative)" : money(after)}</b>
                </div>
              )}
              {a.kind === "price_override" && (
                <div className="impact">Order total {money(a.amount)} · no cash moves</div>
              )}
              {blocked && <div className="impact warn">Vendor won't ship until its open invoice is paid</div>}
              <details className="reason">
                <summary>Why <span style={{ color: by.color }}>{by.label}</span> asked</summary>
                <p>{a.reason}</p>
              </details>
              {a.status === "approved" && <div className="impact warn">Approved but not yet executed. Approve again to retry.</div>}
              <div className="approval-actions">
                <button className="btn approve" disabled={disabled || busyId === a.id} onClick={() => onApprove(a)}>
                  <IconCheck size={14} /> {busyId === a.id ? "Working…" : k.verb}
                </button>
                {a.status === "pending" && (
                  <button className="btn ghost" disabled={disabled || busyId === a.id} onClick={() => onReject(a)}>
                    <IconX size={14} /> Reject
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {history.length > 0 && (
        <div className="history">
          <div className="block-k">Decided</div>
          {history.map((a) => (
            <div key={a.id} className="output-line">
              <span className={`kind-dot k-${a.kind}`} />
              <span>#{a.id} {KIND[a.kind].label}</span>
              <span className="mono">{a.kind !== "price_override" && a.status === "executed" ? `−${money(a.amount)}` : money(a.amount)}</span>
              <span className={`pill tiny st-${a.status}`}>{titleCase(a.status)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
