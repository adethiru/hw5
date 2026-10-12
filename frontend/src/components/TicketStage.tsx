import { useEffect, useState } from "react";
import type { AgentEvent, AgentReport, Approval, Draft, Ticket } from "../types";
import { TICKET_TYPE_LABEL } from "../format";
import { IconPlay, ticketIcon } from "./Icons";
import { StatusPill } from "./TicketList";
import AgentRoster from "./AgentRoster";
import LiveFeed from "./LiveFeed";
import RunSummary from "./RunSummary";

interface Props {
  ticket: Ticket | null;
  runEvents: AgentEvent[];
  running: boolean;
  otherRunActive: boolean;
  decision: AgentReport | null | undefined;
  approvals: Approval[];
  drafts: Draft[];
  onRun: () => void;
}

export default function TicketStage({ ticket, runEvents, running, otherRunActive, decision, approvals, drafts, onRun }: Props) {
  const [tab, setTab] = useState<"live" | "summary">("live");
  const hasRun = runEvents.length > 0;
  const finished = runEvents.some((e) => e.kind === "ticket_end" || e.kind === "ticket_error" || e.kind === "ticket_stopped_usage_limit");

  // jump to Summary when a run finishes; back to Live when one starts / ticket changes
  useEffect(() => { setTab(finished && !running ? "summary" : "live"); }, [ticket?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (running) setTab("live"); }, [running]);
  useEffect(() => { if (finished && !running) setTab("summary"); }, [finished, running]);

  if (!ticket) {
    return <div className="panel stage empty-stage">Select a ticket to begin.</div>;
  }

  return (
    <div className="panel stage">
      <div className={`stage-head type-${ticket.type}`}>
        <div className="stage-title">
          <span className="stage-icon">{ticketIcon(ticket.type, 22)}</span>
          <div>
            <div className="stage-kicker">
              Ticket #{ticket.id} · {TICKET_TYPE_LABEL[ticket.type] ?? ticket.type}
            </div>
            <h1>{ticket.subject}</h1>
            <div className="stage-sub">
              from <b>{ticket.requester}</b>
              {ticket.sku && <> · <span className="mono">{ticket.sku}</span> size {ticket.size} × {ticket.qty}</>}
              {ticket.lease_id != null && <> · lease #{ticket.lease_id}</>}
              {ticket.invoice_id != null && <> · invoice #{ticket.invoice_id}</>}
            </div>
          </div>
        </div>
        <div className="stage-actions">
          <StatusPill ticket={ticket} running={running} />
          <button className="btn primary" onClick={onRun} disabled={running || otherRunActive}>
            <IconPlay size={14} />
            {running ? "Agents working…" : ticket.is_resolved ? "Run again" : "Run agent team"}
          </button>
        </div>
      </div>

      {ticket.notes && (
        <div className="ticket-note">
          <span className="note-k">Ticket notes</span>
          <span className="note-v">{ticket.notes}</span>
        </div>
      )}
      {otherRunActive && <div className="inline-hint">Another ticket is running. Runs go one at a time because tickets share the same cash.</div>}

      <AgentRoster events={runEvents} running={running} />

      <div className="tabs">
        <button className={tab === "live" ? "active" : ""} onClick={() => setTab("live")}>
          Live feed {running && <span className="pulse-dot" />}
        </button>
        <button className={tab === "summary" ? "active" : ""} onClick={() => setTab("summary")} disabled={!hasRun}>
          Run summary
        </button>
      </div>

      {tab === "live" ? (
        <LiveFeed events={runEvents} running={running} />
      ) : (
        <RunSummary events={runEvents} decision={decision ?? null} approvals={approvals} drafts={drafts} />
      )}
    </div>
  );
}
