import type { Actor, AgentName } from "./types";

export interface AgentMeta {
  name: Actor;
  label: string;
  role: string;
  initials: string;
  color: string; // main accent
  soft: string; // tinted background
}

export const AGENTS: Record<Actor, AgentMeta> = {
  boss: { name: "boss", label: "Boss", role: "Routes tickets · final call", initials: "BO", color: "#6d4bd8", soft: "#f1edfd" },
  inventory: { name: "inventory", label: "Inventory", role: "Stock · vendors · restock", initials: "IN", color: "#12875a", soft: "#e7f6ef" },
  accounting: { name: "accounting", label: "Accounting", role: "Cash · margins · approvals", initials: "AC", color: "#c27406", soft: "#fdf3e3" },
  facilities: { name: "facilities", label: "Facilities", role: "Lease · rent · space", initials: "FA", color: "#2563c9", soft: "#e9f0fc" },
  customer_service: { name: "customer_service", label: "Customer Service", role: "Customer drafts", initials: "CS", color: "#cc2f72", soft: "#fcebf2" },
  human: { name: "human", label: "You", role: "Human approver", initials: "YOU", color: "#334155", soft: "#eef1f5" },
  system: { name: "system", label: "System", role: "Backend", initials: "SYS", color: "#64748b", soft: "#f1f5f9" },
};

export const TEAM: AgentName[] = ["boss", "inventory", "accounting", "facilities", "customer_service"];

export const metaFor = (a: string | null | undefined): AgentMeta =>
  AGENTS[(a as Actor) ?? "system"] ?? AGENTS.system;
