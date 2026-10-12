import type { AgentEvent, AgentName, AgentReport, Approval, Draft } from "../types";
import { AGENTS, metaFor } from "../agents";
import { money, titleCase } from "../format";
import { IconShield } from "./Icons";

interface AgentStats {
  agent: AgentName;
  steps: number;
  tools: Record<string, number>;
  askedBy: string[];
  delegatedTo: string[];
  report: AgentReport | null;
}

function collect(events: AgentEvent[]): AgentStats[] {
  const map = new Map<string, AgentStats>();
  const get = (a: string) => {
    if (!map.has(a)) map.set(a, { agent: a as AgentName, steps: 0, tools: {}, askedBy: [], delegatedTo: [], report: null });
    return map.get(a)!;
  };
  for (const e of events) {
    if (!(e.agent in AGENTS) || e.agent === "human" || e.agent === "system") continue;
    if (e.kind === "start") get(e.agent);
    if (e.kind === "said") {
      const s = get(e.agent);
      s.steps += 1;
      for (const c of e.tool_calls ?? []) {
        if (c.tool === "final_result" || c.tool === "delegate_task") continue;
        s.tools[c.tool] = (s.tools[c.tool] ?? 0) + 1;
      }
    }
    if (e.kind === "delegation" && e.to_agent) {
      get(e.agent).delegatedTo.push(e.to_agent);
      get(e.to_agent).askedBy.push(e.agent);
    }
    if (e.kind === "agent_end" && e.output) get(e.agent).report = e.output;
  }
  return [...map.values()];
}

const KIND_LABEL: Record<string, string> = { payment: "Payment", purchase_order: "Purchase order", price_override: "Price override" };

export default function RunSummary({ events, decision, approvals, drafts }: {
  events: AgentEvent[]; decision: AgentReport | null; approvals: Approval[]; drafts: Draft[];
}) {
  const stats = collect(events);
  const bossEnd = [...events].reverse().find((e) => e.kind === "agent_end" && e.agent === "boss");
  const usage = bossEnd?.cumulative_usage;
  const handoffs = events.filter((e) => e.kind === "delegation").length;
  const totalTools = stats.reduce((n, s) => n + Object.values(s.tools).reduce((a, b) => a + b, 0), 0);
  const unused = (Object.keys(AGENTS) as string[]).filter(
    (a) => !["human", "system"].includes(a) && !stats.some((s) => s.agent === a),
  );

  if (!events.length) return <div className="feed empty-feed"><div className="muted">No run yet for this ticket.</div></div>;

  return (
    <div className="summary">
      {decision && (
        <div className="decision-card">
          <div className="decision-top">
            <div className="feed-avatar big" style={{ background: AGENTS.boss.soft, color: AGENTS.boss.color, borderColor: AGENTS.boss.color }}>BO</div>
            <div>
              <div className="decision-k">Boss · final call</div>
              <div className="decision-v">{decision.decision}</div>
            </div>
            <span className={`pill ${decision.final_status === "resolved" ? "resolved" : decision.final_status === "blocked" ? "blocked" : "open"}`}>
              {titleCase(decision.final_status ?? "")}
            </span>
          </div>
          {!!decision.human_actions_needed?.length && (
            <div className="decision-block">
              <div className="block-k"><IconShield size={14} /> Needs you</div>
              <ul>{decision.human_actions_needed.map((h, i) => <li key={i}>{h}</li>)}</ul>
            </div>
          )}
          {!!decision.risks?.length && (
            <div className="decision-block risk">
              <div className="block-k">Risks flagged</div>
              <ul>{decision.risks.map((r, i) => <li key={i}>{r}</li>)}</ul>
            </div>
          )}
        </div>
      )}

      <div className="stat-row">
        <div className="stat"><span>{stats.length}</span>agents used</div>
        <div className="stat"><span>{handoffs}</span>hand-offs</div>
        <div className="stat"><span>{totalTools}</span>MCP tool calls</div>
        <div className="stat"><span>{usage?.total_tokens?.toLocaleString() ?? "—"}</span>tokens</div>
        <div className="stat"><span>{usage?.requests ?? "—"}</span>model requests</div>
      </div>

      <div className="agent-cards">
        {stats.map((s) => {
          const m = metaFor(s.agent);
          const r = s.report;
          return (
            <div key={s.agent} className="agent-card" style={{ ["--c" as string]: m.color, ["--soft" as string]: m.soft }}>
              <div className="agent-card-head">
                <div className="feed-avatar" style={{ background: m.soft, color: m.color, borderColor: m.color }}>{m.initials}</div>
                <div>
                  <div className="agent-card-name">{m.label}</div>
                  <div className="muted small">
                    {s.askedBy.length ? `asked by ${s.askedBy.map((a) => metaFor(a).label).join(", ")}` : "owner"}
                    {" · "}{s.steps} step{s.steps === 1 ? "" : "s"}
                  </div>
                </div>
              </div>
              <div className="agent-card-body">
                <p>{r?.summary ?? r?.decision ?? "No report captured."}</p>
                {r?.recommendation && <p className="rec"><b>Recommendation:</b> {r.recommendation}</p>}
                {!!r?.blockers?.length && <p className="blockers"><b>Blockers:</b> {r.blockers.join("; ")}</p>}
              </div>
              <div className="tool-row">
                {Object.entries(s.tools).map(([t, n]) => (
                  <span key={t} className="tool-chip small"><span className="tool-name">{t}</span>{n > 1 && <span className="count">×{n}</span>}</span>
                ))}
                {s.delegatedTo.map((d, i) => (
                  <span key={`d${i}`} className="tool-chip delegate small">→ {metaFor(d).label}</span>
                ))}
              </div>
              {!!r?.facts?.length && (
                <details className="facts">
                  <summary>{r.facts.length} facts used</summary>
                  <ul>{r.facts.map((f, i) => <li key={i}>{f.statement} <span className="mono muted">· {f.source_tool}</span></li>)}</ul>
                </details>
              )}
            </div>
          );
        })}
      </div>
      {unused.length > 0 && (
        <div className="muted small unused-line">
          Not needed on this ticket: {unused.map((a) => metaFor(a).label).join(", ")}
        </div>
      )}

      {(approvals.length > 0 || drafts.length > 0) && (
        <div className="outputs">
          {approvals.length > 0 && (
            <div>
              <div className="block-k">Prepared for approval</div>
              {approvals.map((a) => (
                <div key={a.id} className="output-line">
                  <span className={`kind-dot k-${a.kind}`} />
                  <span>#{a.id} {KIND_LABEL[a.kind]}</span>
                  <span className="mono">{money(a.amount)}</span>
                  <span className={`pill tiny st-${a.status}`}>{a.status}</span>
                </div>
              ))}
            </div>
          )}
          {drafts.length > 0 && (
            <div>
              <div className="block-k">Customer drafts</div>
              {drafts.map((d) => (
                <div key={d.id} className="output-line">
                  <span className="kind-dot k-draft" />
                  <span>#{d.id} to {d.recipient}</span>
                  <span className="pill tiny st-draft">draft · not sent</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
