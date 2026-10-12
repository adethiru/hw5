export type AgentName = "boss" | "inventory" | "accounting" | "facilities" | "customer_service";
export type Actor = AgentName | "human" | "system";

export interface Ticket {
  id: number;
  type: string;
  requester: string;
  subject: string;
  sku: string | null;
  size: string | null;
  qty: number | null;
  lease_id: number | null;
  invoice_id: number | null;
  status: string;
  notes: string | null;
  created_at: string;
  is_resolved: boolean;
  state: "open" | "resolved";
}

export interface TicketsResponse {
  shop_today: string;
  tickets: Ticket[];
}

export interface Cash {
  account: string;
  balance: number;
  as_of: string;
  shop_today: string;
  open_invoice_total: number;
  pending_payment_requests_total: number;
  cash_after_pending_payments: number;
}

export interface Approval {
  id: number;
  ticket_id: number | null;
  kind: "payment" | "purchase_order" | "price_override";
  target_type: string | null;
  target_id: string | null;
  amount: number;
  details: Record<string, unknown>;
  reason: string;
  requested_by: string;
  status: "pending" | "approved" | "rejected" | "executed";
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  executed_at: string | null;
  payment_id: number | null;
}

export interface Draft {
  id: number;
  ticket_id: number;
  recipient: string;
  subject: string;
  body: string;
  created_by: string;
  status: string;
  created_at: string;
}

export interface Fact {
  statement: string;
  source_tool: string;
}

export interface AgentReport {
  agent?: AgentName;
  ticket_id?: number | null;
  summary?: string;
  facts?: Fact[];
  recommendation?: string;
  approval_request_ids?: number[];
  draft_ids?: number[];
  blockers?: string[];
  needs_human?: boolean;
  // Boss (TicketDecision)
  ticket_type?: string;
  assigned_agents?: AgentName[];
  decision?: string;
  final_status?: string;
  human_actions_needed?: string[];
  risks?: string[];
}

export interface ToolCall {
  tool: string;
  args: unknown;
}

export interface AgentEvent {
  index: number;
  logged_at: string;
  run_id: string | null;
  ticket_id: number | null;
  agent: Actor;
  event: string;
  depth: number | null;
  chain: string[] | null;
  kind: string;
  step?: number;
  model_name?: string | null;
  text?: string;
  tool_calls?: ToolCall[];
  tool_results?: { tool: string; result: string }[];
  output?: AgentReport;
  to_agent?: AgentName;
  reason?: string | null;
  decision?: AgentReport;
  error?: string;
  result?: unknown;
  request_id?: number;
  approved_by?: string;
  usage?: Record<string, number>;
  cumulative_usage?: Record<string, number>;
}

export interface EventsResponse {
  total_records: number;
  next_after: number;
  events: AgentEvent[];
}

export interface Run {
  run_id: string;
  ticket_id: number;
  status: "queued" | "running" | "done" | "error" | "stopped_usage_limit";
  started_at: string;
  finished_at?: string;
  decision?: AgentReport | null;
  error?: string;
  model?: string;
}

export interface Health {
  ok: boolean;
  model: string;
  db: string;
  run_in_progress: boolean;
}
