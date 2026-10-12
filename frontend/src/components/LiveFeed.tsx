import { useEffect, useRef } from "react";
import type { AgentEvent, AgentName } from "../types";
import { AGENTS, metaFor } from "../agents";
import { compactArgs, prettyJson, time, titleCase } from "../format";
import { IconArrow, IconCheck, IconWrench, IconX } from "./Icons";

const WRITE_TOOLS = new Set([
  "request_payment_approval", "request_purchase_order_approval", "request_price_override_approval",
  "save_customer_draft", "update_ticket",
]);

function Avatar({ agent }: { agent: string }) {
  const m = metaFor(agent);
  return (
    <div className="feed-avatar" style={{ background: m.soft, color: m.color, borderColor: m.color }}>
      {m.initials}
    </div>
  );
}

function ToolChip({ name, args }: { name: string; args?: unknown }) {
  const write = WRITE_TOOLS.has(name);
  const delegate = name === "delegate_task";
  return (
    <div className={`tool-chip ${write ? "write" : ""} ${delegate ? "delegate" : ""}`}>
      <IconWrench size={12} />
      <span className="tool-name">{name}</span>
      {args !== undefined && !delegate && <span className="tool-args">({compactArgs(args)})</span>}
    </div>
  );
}

function EventBody({ e }: { e: AgentEvent }) {
  switch (e.kind) {
    case "start":
      return e.depth ? (
        <div className="feed-text muted">Picked up the task.</div>
      ) : (
        <div className="feed-text muted">Reading the ticket…</div>
      );
    case "said": {
      const calls = (e.tool_calls ?? []).filter((c) => c.tool !== "final_result");
      const reported = (e.tool_calls ?? []).some((c) => c.tool === "final_result");
      return (
        <>
          {e.text && <div className="feed-text">{e.text}</div>}
          {calls.length > 0 && (
            <div className="tool-row">
              {calls.map((c, i) => <ToolChip key={i} name={c.tool} args={c.args} />)}
            </div>
          )}
          {reported && <div className="feed-text muted">Submitting structured report…</div>}
        </>
      );
    }
    case "tool_results":
      return (
        <div className="results">
          {(e.tool_results ?? []).filter((r) => r.tool !== "final_result").map((r, i) => (
            <details key={i} className="result">
              <summary><IconCheck size={12} /> <span className="mono">{r.tool}</span> returned</summary>
              <pre>{prettyJson(r.result)}</pre>
            </details>
          ))}
        </div>
      );
    case "delegation": {
      const to = AGENTS[e.to_agent as AgentName];
      return (
        <div className="delegation" style={{ borderColor: to?.color }}>
          <div className="delegation-head">
            <IconArrow size={14} /> Hand-off to <b style={{ color: to?.color }}>{to?.label ?? e.to_agent}</b>
          </div>
          <div className="delegation-task">{e.text}</div>
        </div>
      );
    }
    case "delegation_refused":
      return <div className="feed-text warn"><IconX size={12} /> Hand-off to {e.to_agent} refused: {e.reason}</div>;
    case "agent_end": {
      const o = e.output;
      return (
        <div className="report">
          <div className="report-k">Report</div>
          <div className="report-v">{o?.summary ?? o?.decision ?? "Finished."}</div>
          {o?.recommendation && <div className="report-rec"><b>Recommends:</b> {o.recommendation}</div>}
        </div>
      );
    }
    case "ticket_start":
      return <div className="feed-text muted">Run started on {e.ticket_id != null ? `ticket #${e.ticket_id}` : "ticket"}.</div>;
    case "ticket_end":
      return <div className="feed-text"><b>Final call:</b> {e.decision?.decision}</div>;
    case "ticket_marked_resolved":
      return <div className="feed-text good">Ticket marked <b>resolved</b> on the board.</div>;
    case "human_decision":
    case "human_payment":
    case "human_purchase_order":
      return <div className="feed-text">{titleCase(e.kind.replace("human_", ""))} by <b>{e.approved_by}</b> on request #{e.request_id}</div>;
    case "agent_error":
    case "ticket_error":
    case "ticket_stopped_usage_limit":
      return <div className="feed-text bad">{titleCase(e.kind)}: {e.error}</div>;
    default:
      return <div className="feed-text muted">{titleCase(e.kind)}</div>;
  }
}

export default function LiveFeed({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const shown = events.filter((e) => e.kind !== "final");

  useEffect(() => {
    const el = ref.current;
    if (el && running) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [shown.length, running]);

  if (!shown.length) {
    return (
      <div className="feed empty-feed">
        <div className="empty-art">
          {(["boss", "inventory", "accounting", "facilities", "customer_service"] as AgentName[]).map((a) => (
            <span key={a} style={{ background: AGENTS[a].soft, color: AGENTS[a].color }}>{AGENTS[a].initials}</span>
          ))}
        </div>
        <div className="empty-title">The team is standing by</div>
        <div className="muted">Press <b>Run agent team</b>. Every step the agents take will stream in here.</div>
      </div>
    );
  }

  return (
    <div className="feed" ref={ref}>
      {shown.map((e) => {
        const m = metaFor(e.agent);
        const depth = Math.min(e.depth ?? 0, 3);
        const system = e.kind.startsWith("ticket_") || e.agent === "system";
        return (
          <div
            key={e.index}
            className={`feed-row k-${e.kind} ${system ? "system" : ""}`}
            style={{ ["--c" as string]: m.color, ["--soft" as string]: m.soft, marginLeft: depth * 22 }}
          >
            <Avatar agent={e.agent} />
            <div className="feed-main">
              <div className="feed-head">
                <span className="feed-agent" style={{ color: m.color }}>{m.label}</span>
                {e.kind === "said" && e.step != null && <span className="feed-step">step {e.step}</span>}
                {e.chain && e.chain.length > 1 && (
                  <span className="feed-chain">{e.chain.map((c) => metaFor(c).label).join(" › ")}</span>
                )}
                <span className="feed-time">{time(e.logged_at)}</span>
              </div>
              <EventBody e={e} />
            </div>
          </div>
        );
      })}
      {running && (
        <div className="feed-row thinking-row">
          <span className="typing"><i /><i /><i /></span>
          <span className="muted small">agents are working…</span>
        </div>
      )}
    </div>
  );
}
