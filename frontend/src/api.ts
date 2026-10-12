// Thin client for the FastAPI routes in backend/main.py (Problem 7).
import type {
  Approval, Cash, Draft, EventsResponse, Health, Run, TicketsResponse,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// The FastAPI backend (Problem 7). Override with VITE_API_BASE in frontend/.env if needed.
export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<Health>("/api/health"),
  tickets: () => req<TicketsResponse>("/api/tickets"),
  runTicket: (id: number) => req<Run>(`/api/tickets/${id}/run`, { method: "POST" }),
  run: (runId: string) => req<Run>(`/api/runs/${runId}`),
  runs: () => req<{ runs: Run[] }>("/api/runs"),
  events: (after = -1, limit = 1000) =>
    req<EventsResponse>(`/api/events?after=${after}&limit=${limit}`),
  approvals: () => req<{ count: number; approval_requests: Approval[] }>("/api/approvals?status=all"),
  drafts: () => req<{ count: number; customer_drafts: Draft[] }>("/api/drafts"),
  approve: (id: number, approvedBy: string, note = "") =>
    req<{ result: unknown; cash: Cash; kind: string }>(`/api/approvals/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ approved_by: approvedBy, note }),
    }),
  reject: (id: number, approvedBy: string, note = "") =>
    req<unknown>(`/api/approvals/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ approved_by: approvedBy, note }),
    }),
  cash: () => req<Cash>("/api/cash"),
  reset: () => req<{ ok: boolean; cash: Cash }>("/api/reset", { method: "POST" }),
};
