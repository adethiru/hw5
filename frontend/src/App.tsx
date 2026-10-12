import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "./api";
import type { AgentEvent, Approval, Cash, Draft, Health, Run, Ticket } from "./types";
import { money } from "./format";
import Header from "./components/Header";
import TicketList from "./components/TicketList";
import TicketStage from "./components/TicketStage";
import ApprovalsPanel from "./components/ApprovalsPanel";
import CashPanel from "./components/CashPanel";
import DraftsPanel from "./components/DraftsPanel";
import Toasts, { type Toast } from "./components/Toasts";

const BASE_POLL_MS = 4000;
const LIVE_POLL_MS = 1200;

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [shopToday, setShopToday] = useState<string>("");
  const [cash, setCash] = useState<Cash | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const cursor = useRef(-1);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [activeRun, setActiveRun] = useState<Run | null>(null);
  const [finishedRuns, setFinishedRuns] = useState<Record<number, Run>>({});
  const [approver, setApprover] = useState("");
  const [busyApproval, setBusyApproval] = useState<number | null>(null);
  const [resetting, setResetting] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [cashFlash, setCashFlash] = useState<null | "down">(null);
  const prevBalance = useRef<number | null>(null);

  const toast = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((ts) => [...ts, { ...t, id }]);
    setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), 6000);
  }, []);

  // ------------------------------------------------------------ data loaders
  const loadBoard = useCallback(async () => {
    try {
      const [h, t, c, a, d] = await Promise.all([
        api.health(), api.tickets(), api.cash(), api.approvals(), api.drafts(),
      ]);
      setHealth(h);
      setTickets(t.tickets);
      setShopToday(t.shop_today);
      setCash(c);
      setApprovals(a.approval_requests);
      setDrafts(d.customer_drafts);
      setOffline(false);
      setSelectedId((cur) => cur ?? t.tickets[0]?.id ?? null);
    } catch {
      setOffline(true);
    }
  }, []);

  const loadEvents = useCallback(async () => {
    try {
      const r = await api.events(cursor.current, 1000);
      if (r.next_after < cursor.current) {
        // audit file was replaced; reload everything
        cursor.current = -1;
        const all = await api.events(-1, 1000);
        setEvents(all.events);
        cursor.current = all.next_after;
        return;
      }
      if (r.events.length) setEvents((ev) => [...ev, ...r.events]);
      cursor.current = r.next_after;
    } catch {
      /* backend offline - handled by loadBoard */
    }
  }, []);

  // initial load + reattach to a run already in progress
  useEffect(() => {
    loadBoard();
    loadEvents();
    api.runs()
      .then(({ runs }) => {
        const live = runs.find((r) => r.status === "running" || r.status === "queued");
        if (live) {
          setActiveRun(live);
          setSelectedId(live.ticket_id);
        }
        const done: Record<number, Run> = {};
        [...runs].reverse().forEach((r) => {
          if (r.status !== "running" && r.status !== "queued") done[r.ticket_id] = r;
        });
        setFinishedRuns(done);
      })
      .catch(() => undefined);
  }, [loadBoard, loadEvents]);

  // slow poll for the board
  useEffect(() => {
    const id = setInterval(() => {
      loadBoard();
      loadEvents();
    }, BASE_POLL_MS);
    return () => clearInterval(id);
  }, [loadBoard, loadEvents]);

  // fast poll while agents are working
  const running = activeRun?.status === "running" || activeRun?.status === "queued";
  useEffect(() => {
    if (!running || !activeRun) return;
    const id = setInterval(async () => {
      await loadEvents();
      try {
        const r = await api.run(activeRun.run_id);
        if (r.status === "running" || r.status === "queued") {
          setActiveRun(r);
          return;
        }
        setActiveRun(null);
        setFinishedRuns((f) => ({ ...f, [r.ticket_id]: r }));
        await loadBoard();
        await loadEvents();
        if (r.status === "done") {
          toast({ tone: "success", title: `Ticket ${r.ticket_id} resolved`, body: "The team finished. Review approvals on the right." });
        } else {
          toast({ tone: "error", title: `Ticket ${r.ticket_id} run ${r.status.replace(/_/g, " ")}`, body: r.error ?? "See the live feed for details." });
        }
      } catch {
        /* keep polling */
      }
    }, LIVE_POLL_MS);
    return () => clearInterval(id);
  }, [running, activeRun, loadBoard, loadEvents, toast]);

  // flash the cash card when the balance drops
  useEffect(() => {
    if (!cash) return;
    if (prevBalance.current !== null && cash.balance < prevBalance.current) {
      setCashFlash("down");
      setTimeout(() => setCashFlash(null), 2200);
    }
    prevBalance.current = cash.balance;
  }, [cash]);

  // ------------------------------------------------------------ actions
  const startRun = async (ticketId: number) => {
    try {
      const r = await api.runTicket(ticketId);
      setActiveRun(r);
      setSelectedId(ticketId);
      toast({ tone: "info", title: `Agents started on ticket ${ticketId}`, body: "The Boss is reading the ticket." });
      loadEvents();
    } catch (e) {
      toast({ tone: "error", title: "Could not start run", body: (e as Error).message });
    }
  };

  const decide = async (a: Approval, decision: "approve" | "reject") => {
    if (!approver.trim()) {
      toast({ tone: "error", title: "Who is approving?", body: "Enter your name in the Approvals panel first." });
      return;
    }
    setBusyApproval(a.id);
    try {
      if (decision === "approve") {
        const r = await api.approve(a.id, approver.trim());
        setCash(r.cash);
        if (a.kind === "payment") {
          toast({ tone: "success", title: `Paid ${money(a.amount)}`, body: `Checking is now ${money(r.cash.balance)}. Approved by ${approver.trim()}.` });
        } else if (a.kind === "purchase_order") {
          toast({ tone: "success", title: `Purchase order placed · ${money(a.amount)}`, body: `Prepaid. Checking is now ${money(r.cash.balance)}. Simulated; no vendor contacted.` });
        } else {
          toast({ tone: "success", title: "Price override approved", body: `Request #${a.id} approved by ${approver.trim()}.` });
        }
      } else {
        await api.reject(a.id, approver.trim());
        toast({ tone: "info", title: `Request #${a.id} rejected` });
      }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message;
      toast({ tone: "error", title: "Refused", body: msg });
    } finally {
      setBusyApproval(null);
      loadBoard();
      loadEvents();
    }
  };

  const reset = async () => {
    if (!confirm("Reset the working database to the original values? Pending approvals and drafts will be cleared. The audit trail is kept.")) return;
    setResetting(true);
    try {
      const r = await api.reset();
      setCash(r.cash);
      setFinishedRuns({});
      prevBalance.current = r.cash.balance;
      toast({ tone: "info", title: "Database reset", body: `Checking back to ${money(r.cash.balance)}.` });
      await loadBoard();
    } catch (e) {
      toast({ tone: "error", title: "Reset failed", body: (e as Error).message });
    } finally {
      setResetting(false);
    }
  };

  // ------------------------------------------------------------ derived
  const selected = tickets.find((t) => t.id === selectedId) ?? null;

  const ticketEvents = useMemo(
    () => events.filter((e) => e.ticket_id === selectedId),
    [events, selectedId],
  );

  const latestRunId = useMemo(() => {
    if (activeRun && activeRun.ticket_id === selectedId) return activeRun.run_id;
    for (let i = ticketEvents.length - 1; i >= 0; i--) {
      if (ticketEvents[i].kind === "ticket_start" && ticketEvents[i].run_id) return ticketEvents[i].run_id;
    }
    return null;
  }, [activeRun, selectedId, ticketEvents]);

  const runEvents = useMemo(
    () => (latestRunId ? ticketEvents.filter((e) => e.run_id === latestRunId) : []),
    [ticketEvents, latestRunId],
  );

  const pendingByTicket = useMemo(() => {
    const m: Record<number, number> = {};
    approvals.forEach((a) => {
      const open = a.status === "pending" || (a.status === "approved" && a.kind !== "price_override");
      if (open && a.ticket_id != null) m[a.ticket_id] = (m[a.ticket_id] ?? 0) + 1;
    });
    return m;
  }, [approvals]);

  const selectedRunning = running && activeRun?.ticket_id === selectedId;
  const decision =
    runEvents.find((e) => e.kind === "ticket_end")?.decision ??
    (selectedId != null ? finishedRuns[selectedId]?.decision ?? null : null);

  return (
    <div className="app">
      <Header
        health={health}
        offline={offline}
        shopToday={shopToday}
        cash={cash}
        cashFlash={cashFlash}
        onReset={reset}
        resetting={resetting}
        runBusy={running}
      />

      {offline && (
        <div className="offline-banner">
          Can't reach the backend at <code>http://localhost:8000</code>. Start it from <code>backend/</code> with{" "}
          <code>uvicorn main:app --reload --port 8000</code>.
        </div>
      )}

      <main className="layout">
        <aside className="col col-left">
          <TicketList
            tickets={tickets}
            selectedId={selectedId}
            onSelect={setSelectedId}
            runningTicketId={running ? activeRun?.ticket_id ?? null : null}
            pendingByTicket={pendingByTicket}
          />
        </aside>

        <section className="col col-center">
          <TicketStage
            ticket={selected}
            runEvents={runEvents}
            running={!!selectedRunning}
            otherRunActive={running && !selectedRunning}
            decision={decision}
            approvals={approvals.filter((a) => a.ticket_id === selectedId)}
            drafts={drafts.filter((d) => d.ticket_id === selectedId)}
            onRun={() => selected && startRun(selected.id)}
          />
        </section>

        <aside className="col col-right">
          <ApprovalsPanel
            approvals={approvals}
            cash={cash}
            approver={approver}
            setApprover={setApprover}
            busyId={busyApproval}
            disabled={running}
            selectedTicketId={selectedId}
            onApprove={(a) => decide(a, "approve")}
            onReject={(a) => decide(a, "reject")}
          />
          <CashPanel cash={cash} approvals={approvals} />
          <DraftsPanel drafts={drafts} ticketId={selectedId} />
        </aside>
      </main>

      <Toasts toasts={toasts} onDismiss={(id) => setToasts((ts) => ts.filter((t) => t.id !== id))} />
    </div>
  );
}
