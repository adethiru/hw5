import type { Ticket } from "../types";
import { TICKET_TYPE_LABEL } from "../format";
import { ticketIcon } from "./Icons";

interface Props {
  tickets: Ticket[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  runningTicketId: number | null;
  pendingByTicket: Record<number, number>;
}

export function StatusPill({ ticket, running }: { ticket: Ticket; running: boolean }) {
  if (running) return <span className="pill running"><span className="pulse-dot" /> Running</span>;
  if (ticket.is_resolved) return <span className="pill resolved">Resolved</span>;
  if (ticket.status === "blocked") return <span className="pill blocked">Blocked</span>;
  return <span className="pill open">Open</span>;
}

export default function TicketList({ tickets, selectedId, onSelect, runningTicketId, pendingByTicket }: Props) {
  const resolved = tickets.filter((t) => t.is_resolved).length;
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Ticket board</h2>
        <span className="muted small">{resolved}/{tickets.length} resolved</span>
      </div>
      <div className="progress"><div style={{ width: `${tickets.length ? (resolved / tickets.length) * 100 : 0}%` }} /></div>

      <div className="ticket-list">
        {tickets.map((t) => {
          const running = runningTicketId === t.id;
          const pending = pendingByTicket[t.id] ?? 0;
          return (
            <button
              key={t.id}
              className={`ticket-card type-${t.type} ${selectedId === t.id ? "selected" : ""} ${running ? "is-running" : ""}`}
              onClick={() => onSelect(t.id)}
            >
              <div className="ticket-top">
                <span className="ticket-icon">{ticketIcon(t.type)}</span>
                <span className="ticket-id">#{t.id}</span>
                <StatusPill ticket={t} running={running} />
              </div>
              <div className="ticket-subject">{t.subject}</div>
              <div className="ticket-meta">
                <span>{TICKET_TYPE_LABEL[t.type] ?? t.type}</span>
                <span className="sep">·</span>
                <span>{t.requester}</span>
              </div>
              <div className="ticket-tags">
                {t.sku && <span className="tag mono">{t.sku} · {t.size} × {t.qty}</span>}
                {t.lease_id != null && <span className="tag">Lease #{t.lease_id}</span>}
                {t.invoice_id != null && <span className="tag">Invoice #{t.invoice_id}</span>}
                {pending > 0 && <span className="tag warn">{pending} awaiting you</span>}
              </div>
            </button>
          );
        })}
        {tickets.length === 0 && <div className="empty">No tickets loaded yet.</div>}
      </div>

      <div className="legend-box">
        <div className="legend-title">How it works</div>
        <ol>
          <li>Pick a ticket and press <b>Run agent team</b>.</li>
          <li>Watch the Boss delegate in the live feed.</li>
          <li>Approve or reject what Accounting prepared. Only an approval moves cash.</li>
        </ol>
      </div>
    </div>
  );
}
