import type { AgentEvent, AgentName } from "../types";
import { AGENTS, TEAM } from "../agents";
import { IconCheck } from "./Icons";

type Status = "idle" | "thinking" | "done" | "unused";

/** Derive each agent's state from the run's events. */
export function agentStatuses(events: AgentEvent[], running: boolean) {
  const open: Record<string, number> = {};
  const seen = new Set<string>();
  const lastLine: Record<string, string> = {};
  for (const e of events) {
    if (!e.agent) continue;
    if (e.kind === "start") {
      open[e.agent] = (open[e.agent] ?? 0) + 1;
      seen.add(e.agent);
    } else if (e.kind === "agent_end") {
      open[e.agent] = Math.max(0, (open[e.agent] ?? 1) - 1);
    } else if (e.kind === "said") {
      if (e.tool_calls?.length) {
        const names = e.tool_calls.map((t) => t.tool).filter((t) => t !== "final_result");
        lastLine[e.agent] = names.length ? `calling ${names.join(", ")}` : "writing report";
      } else if (e.text) lastLine[e.agent] = e.text.slice(0, 80);
    } else if (e.kind === "delegation") {
      lastLine[e.agent] = `asked ${AGENTS[e.to_agent as AgentName]?.label ?? e.to_agent}`;
    }
  }
  // The agent currently "holding the mic" = most recent event from an agent whose loop is still open.
  let current: string | null = null;
  for (let i = events.length - 1; i >= 0; i--) {
    const a = events[i].agent;
    if (a && (open[a] ?? 0) > 0) { current = a; break; }
  }
  const status: Record<AgentName, Status> = {} as Record<AgentName, Status>;
  TEAM.forEach((a) => {
    if (!seen.has(a)) status[a] = events.length ? "unused" : "idle";
    else if (running && (open[a] ?? 0) > 0) status[a] = "thinking";
    else status[a] = "done";
  });
  return { status, current: running ? current : null, lastLine };
}

export default function AgentRoster({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const { status, current, lastLine } = agentStatuses(events, running);
  const delegations = events.filter((e) => e.kind === "delegation");

  return (
    <div className="roster-wrap">
      <div className="roster">
        {TEAM.map((a) => {
          const m = AGENTS[a];
          const s = status[a];
          const isCurrent = current === a;
          return (
            <div
              key={a}
              className={`agent-node s-${s} ${isCurrent ? "current" : ""}`}
              style={{ ["--c" as string]: m.color, ["--soft" as string]: m.soft }}
            >
              <div className="avatar">
                {m.initials}
                {s === "done" && <span className="badge-done"><IconCheck size={10} /></span>}
              </div>
              <div className="agent-label">{m.label}</div>
              <div className="agent-state">
                {s === "thinking" ? (isCurrent ? <span className="typing"><i /><i /><i /></span> : "waiting on teammate")
                  : s === "done" ? "done"
                  : s === "unused" ? "not needed"
                  : m.role}
              </div>
              {isCurrent && lastLine[a] && <div className="agent-bubble">{lastLine[a]}</div>}
            </div>
          );
        })}
      </div>
      {delegations.length > 0 && (
        <div className="handoffs">
          <span className="handoffs-k">Hand-offs</span>
          {delegations.map((d) => {
            const from = AGENTS[d.agent as AgentName];
            const to = AGENTS[d.to_agent as AgentName];
            return (
              <span key={d.index} className="handoff">
                <b style={{ color: from?.color }}>{from?.label ?? d.agent}</b>
                <span className="arrow">→</span>
                <b style={{ color: to?.color }}>{to?.label ?? d.to_agent}</b>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
