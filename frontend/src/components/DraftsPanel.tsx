import type { Draft } from "../types";
import { IconMail } from "./Icons";

export default function DraftsPanel({ drafts, ticketId }: { drafts: Draft[]; ticketId: number | null }) {
  const mine = drafts.filter((d) => d.ticket_id === ticketId);
  return (
    <div className="panel drafts">
      <div className="panel-head">
        <h2><IconMail size={16} /> Customer drafts</h2>
        <span className="muted small">ticket #{ticketId ?? "—"}</span>
      </div>
      {mine.length === 0 && <div className="empty small">No drafts for this ticket yet.</div>}
      {mine.map((d) => (
        <div key={d.id} className="letter">
          <div className="letter-stamp">DRAFT · NOT SENT</div>
          <div className="letter-to">To: <b>{d.recipient}</b></div>
          <div className="letter-subj">{d.subject}</div>
          <div className="letter-body">{d.body}</div>
        </div>
      ))}
    </div>
  );
}
