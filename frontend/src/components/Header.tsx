import { useEffect, useRef, useState } from "react";
import type { Cash, Health } from "../types";
import { money } from "../format";
import { IconRefresh, IconWallet } from "./Icons";

function useTween(target: number | null, ms = 900) {
  const [value, setValue] = useState<number | null>(target);
  const from = useRef<number | null>(target);
  useEffect(() => {
    if (target == null) return;
    const start = from.current ?? target;
    if (start === target) {
      setValue(target);
      return;
    }
    const t0 = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / ms);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(start + (target - start) * eased);
      if (p < 1) raf = requestAnimationFrame(step);
      else from.current = target;
    };
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      from.current = target;
    };
  }, [target, ms]);
  return value;
}

interface Props {
  health: Health | null;
  offline: boolean;
  shopToday: string;
  cash: Cash | null;
  cashFlash: null | "down";
  onReset: () => void;
  resetting: boolean;
  runBusy: boolean;
}

export default function Header({ health, offline, shopToday, cash, cashFlash, onReset, resetting, runBusy }: Props) {
  const balance = useTween(cash?.balance ?? null);
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">CC</div>
        <div>
          <div className="brand-name">Campus Customs</div>
          <div className="brand-sub">Multi-Agent Operations Desk</div>
        </div>
      </div>

      <div className="topbar-meta">
        <div className="meta-pill">
          <span className="meta-k">Shop date</span>
          <span className="meta-v">{shopToday || "—"}</span>
        </div>
        <div className="meta-pill">
          <span className="meta-k">Model</span>
          <span className="meta-v mono">{health?.model ?? "—"}</span>
        </div>
        <div className={`meta-pill status ${offline ? "bad" : runBusy ? "busy" : "good"}`}>
          <span className="dot" />
          <span className="meta-v">{offline ? "Backend offline" : runBusy ? "Agents working" : "Backend ready"}</span>
        </div>
      </div>

      <div className="topbar-right">
        <div className={`cash-card ${cashFlash === "down" ? "flash-down" : ""}`}>
          <div className="cash-icon"><IconWallet size={20} /></div>
          <div>
            <div className="cash-label">Checking balance</div>
            <div className="cash-value">{money(balance)}</div>
            {cash && (
              <div className="cash-sub">
                {cash.pending_payment_requests_total > 0
                  ? <>After queued payments: <b>{money(cash.cash_after_pending_payments)}</b></>
                  : <>as of {cash.as_of}</>}
              </div>
            )}
          </div>
        </div>
        <button className="btn ghost light" onClick={onReset} disabled={resetting || runBusy} title="Copy campus_customs.db over the working copy">
          <IconRefresh size={15} className={resetting ? "spin" : ""} /> Reset DB
        </button>
      </div>
    </header>
  );
}
