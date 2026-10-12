# Campus Customs · Ops Desk: Dashboard Design

The dashboard (`frontend/`, React + Vite + TypeScript) is where a human watches five AI agents run a small shop and stays in charge of the money.

It has to work as two things at once:

1. **Mission control.** You can see who is working, what they're doing, and why.
2. **A checkbook.** Nothing leaves the account until a person clicks Approve, and when they do, the drop in cash is impossible to miss.

Every design choice below serves one of those two jobs.

---

## 1. Design principles

| Principle | What it means on screen |
|---|---|
| **The human is in charge** | The approvals panel and the cash balance are always visible. Agents *prepare*; only the human *spends*. The wording says so ("Agents only prepare these. Nothing is paid or ordered until you approve."). |
| **Show the work, not just the answer** | Each tool call, hand-off and report streams in live, so you can check that the agents used real data (the MCP tool names and arguments are right there). |
| **Each agent is a person you can recognize** | Five agents, five colors, five avatars, used the same way everywhere: roster, feed, summary and approval reasons. |
| **Calm by default, loud when it matters** | A soft, light canvas. Strong color and motion appear only for what needs attention: the agent currently thinking, a pending approval, a cash drop, an error. |
| **No dead ends** | Empty states explain what to do next. Refusals, such as "would go negative", explain *why*, in plain words. |

---

## 2. Layout: three columns, one story

```
┌──────────────────────────────── Top bar (sticky) ────────────────────────────────┐
│ CC Campus Customs   [Shop date] [Model gpt-6-luna] [● status]   [$ Checking] [Reset] │
├──────────────┬───────────────────────────────────────────────┬───────────────────┤
│ TICKET BOARD │  TICKET STAGE                                 │  APPROVALS  (2)   │
│ ▓▓▓░░ 1/3    │  #101 · Customer order                        │  approver: [Ade]  │
│ ┃#101 Running│  Bulldog tee            [Running] [▶ Run]     │  ┌ PAYMENT $840 ┐ │
│ ┃#102 Resolvd│  ┌BO┐ ┌IN✓┐ ┌AC…┐ ┌FA┐ ┌CS┐   ← agent roster   │  │ 3,400→2,560  │ │
│ ┃#103 Open   │  Hand-offs: Boss→Inventory  Boss→Accounting   │  │[Approve&pay] │ │
│              │  [Live feed •] [Run summary]                  │  └──────────────┘ │
│ How it works │  BO get_ticket(ticket_id=101)                 │  CASH  $3,400     │
│ 1. Pick…     │  BO → Hand-off to Inventory: "…"              │  ▁▁▁▔▔╲__ ledger  │
│ 2. Watch…    │    IN check_inventory_stock(sku=…, size="S")  │  CUSTOMER DRAFTS  │
│ 3. Approve…  │    IN Report: 0 on hand, shortfall 1 …        │  ✉ DRAFT·NOT SENT │
└──────────────┴───────────────────────────────────────────────┴───────────────────┘
```

**Why three columns?** They follow the order a human actually works in:

- **Left, pick:** what needs doing.
- **Center, watch:** the team doing it.
- **Right, decide:** what needs *me*.

Your eyes move left to right, the same way the work flows. The side columns are sticky with their own scroll, so the Approve button and the balance never scroll out of view during a long run.

**Responsive.**

- Under 1280 px, the right column moves below the stage as a card grid.
- Under 860 px, everything stacks into one column in the same order: tickets, stage, approvals.
- The top bar stays sticky, so the checking balance is always one glance away.

---

## 3. How the agents read differently

Each agent has an identity that stays the same across the whole app:

| Agent | Color | Avatar | Why this color |
|---|---|---|---|
| **Boss** | Violet `#6d4bd8` | BO | Violet sits outside the "operations" palette. The coordinator is visually *above* the specialists. |
| **Inventory** | Emerald `#12875a` | IN | Green = stock on the shelf, go or no-go. |
| **Accounting** | Amber `#c27406` | AC | Amber = money and caution. This agent prepares things that cost cash. |
| **Facilities** | Blue `#2563c9` | FA | Blue = the building, steady and structural. |
| **Customer Service** | Rose `#cc2f72` | CS | Warm and human; this agent is the voice customers hear. |
| You (human) / System | Slate | YOU / SYS | Neutral, so they never compete with the agents. |

The same color carries through every place the agent appears:

- the roster card border and avatar
- the feed name
- the report box tint
- the summary card's top stripe
- the "Why *Accounting* asked" link on an approval

After one run, you can tell who said something by color alone.

### The agent roster (center, top)

The roster has five cards, one per agent. Each has four states, and every state is drawn differently:

- **Standing by:** a neutral card showing the agent's job ("Stock · vendors · restock").
- **Thinking (holding the mic):** the card lifts, fills with the agent's tint, and the avatar turns solid with a pulsing ring. A small dark speech bubble underneath says what it's doing right now ("calling check_inventory_stock", "asked Accounting"). Exactly one agent holds the mic at a time, so you always know who is speaking.
- **Waiting on teammate:** an agent that delegated and is waiting for an answer keeps a soft tint and says "waiting on teammate". You can see the call stack, for example Boss waiting on Accounting.
- **Done:** a small green check badge appears on the avatar.
- **Not needed:** the card fades to about 40% and turns grey. This deliberately shows that the Boss *didn't* send every specialist, which is the efficiency the plan in `desk_tickets.html` is graded on. On ticket 102, for example, Inventory and Customer Service visibly sit out.

Under the roster, a **hand-offs strip** lists each delegation in order as colored "Boss → Inventory" pills. That's the full routing of the ticket in one line.

### The live feed

- **One row per agent-loop step.** Each row has the avatar, the colored name, a step number, the delegation chain ("Boss › Inventory") and a timestamp.
- **Indentation follows the delegation depth.** A teammate's steps are indented under the agent that asked, so the conversation reads like a threaded discussion.
- **Tool calls are code-styled chips** showing the real MCP tool name and its arguments, for example `check_inventory_stock(sku="CC-TEE-WHITE", size="S", qty_needed=1)`.
  - **Blue chips** are reads.
  - **Amber chips** are tools that write to the board (`request_payment_approval`, `save_customer_draft`, `update_ticket`), so actions with consequences stand out.
  - **Violet chips** are delegations.
- **Tool results** are collapsed by default ("✓ check_vendor_status returned · show") and open as dark code blocks with pretty-printed JSON. The feed stays readable, and the receipts are one click away.
- **Hand-offs** appear as a card with a colored left border in the receiving agent's color, quoting the exact task text the agent wrote.
- **Reports**, when an agent finishes, are a tinted box with the summary and a bold "Recommends: …" line.
- **Motion:** new rows fade up gently, the feed auto-scrolls while running, and a "typing" indicator sits at the bottom so the page never looks frozen during a slow model call.

---

## 4. How resolved tickets show up

Several signals reinforce each other, so you can't miss a ticket being resolved:

1. **Status pills** use the same colors everywhere: grey *Open*, amber *Running* with a pulsing dot, green *Resolved*, red *Blocked*.
2. **Ticket cards** have a left stripe in the ticket type's color (order = emerald, rent = blue, discount = amber). While a ticket runs, a light sweep animates along the card's bottom edge, so you can spot the running ticket from across the room.
3. **The board progress bar** ("1/3 resolved") fills in green as tickets finish. It's a small sense of progress, the "inbox zero" feeling.
4. **When a run ends:**
   - a green toast says "Ticket 101 resolved"
   - the pill flips to Resolved
   - the stage **switches automatically to the Run summary tab**

   You go straight from watching to reviewing.
5. **The Run summary** is the ticket's report card:
   - **Boss's final call** in a violet-tinted card. It shows the decision, the status pill, a **"Needs you"** list (exactly which approvals to act on) and a **"Risks flagged"** box, such as only $160 left if both bills are paid.
   - **A stat row:** agents used, hand-offs, MCP tool calls, tokens and model requests. Token use is visible, which supports the cost guardrails.
   - **One card per agent that worked,** with "asked by Boss · 3 steps", its summary and recommendation, tool chips with counts (×2), any delegations, and a collapsible "N facts used" list where each fact shows its source tool.
   - **"Not needed on this ticket: Facilities"**, so efficiency is shown, not just claimed.
   - **"Prepared for approval"** and **"Customer drafts"**, which list what the run produced with live status pills (pending → executed).
6. **"Resolved" doesn't mean the money moved.** The ticket is resolved when the agents' work is done. Anything still waiting on the human keeps an amber **"1 awaiting you"** tag on the ticket card until approved. The board stays honest about what is finished and what needs a person.

---

## 5. How cash shows up

Cash appears in three places, each with its own job:

1. **The top-bar balance card** is always visible.
   - It shows the checking balance in large tabular numbers, plus "After queued payments: $X" when requests are pending, so you see the future, not just the present.
   - **When a payment is approved, the number animates down** (a 0.9 s ease-out count), and the card **flashes red and scales up slightly** for about 2 seconds. A falling number is felt, not just read. That moment is the whole point of human approval, so it gets a deliberate moment of weight.
2. **Each payment approval card previews its impact before you click:** "Checking $3,400.00 → **$2,560.00**". If a payment would overdraw the account, the preview turns red and says "refused (would go negative)" before you even try. The backend refuses too, and the toast explains why. Purchase orders show "Vendor won't ship until its open invoice is paid", and price overrides say "no cash moves".
3. **The Cash panel** is the ledger view:
   - the big balance
   - a progress bar of what's left versus the opening balance
   - a **sparkline** that steps down with each executed payment
   - a ledger: Opening → each payment ("Bulldog Print Co · by Ade −$840.00") → **Now**, then open invoices owed, queued for approval, and "If all queued are paid" (red if negative)

   The note "no revenue modeled, cash only goes out" sets expectations.

The approve button is **green and labeled with what it does**: "Approve & pay", "Approve & order" or "Approve price". There's never an ambiguous "OK". Reject is a quieter ghost button next to it. An **"Approving as" name field** is required, because the backend records `approved_by` in the `payments` table and refuses agent names. A toast confirms the outcome: "Paid $840.00. Checking is now $2,560.00. Approved by Ade."

---

## 6. Details that make it pleasant to use

- **Customer drafts look like letters.** They're on cream lined paper, the body is in a serif font, and a tilted rose **"DRAFT · NOT SENT"** stamp makes it obvious that nothing went to a real customer.
- **The empty state has personality.** Before a run, the five agent avatars sit in an overlapping row with "The team is standing by".
- **The header tells you about the backend.** The status dot is green "Backend ready", amber pulsing "Agents working" or red "Backend offline". If offline, a banner gives the exact `uvicorn` command to start it.
- **Safe controls.** Reset asks for confirmation and explains what it clears (the audit trail is kept). Run, approve and reset are disabled while another ticket is running, with a hint: "Runs go one at a time because tickets share the same cash."
- **It picks up where it left off.** Reloading the page mid-run reattaches to the run in progress.
- **Typography and numbers.** It uses a system sans-serif with mono for tool names and SKUs. Money uses `font-variant-numeric: tabular-nums`, so digits don't jitter while animating.
- **Accessibility.** Text colors pass WCAG AA contrast on their backgrounds, and states are never shown by color alone (there's always a word: "Resolved", "done", "not needed"). `prefers-reduced-motion` turns off every animation.
- **Few dependencies.** It uses only React, with hand-written CSS and a tiny inline SVG icon set. No UI kit means a fast install, a unique look, and nothing to break on `npm install`.

---

## 7. How it connects

- The page calls the FastAPI backend directly at **`http://localhost:8000`** (`src/api.ts`). This can be overridden with `VITE_API_BASE`.
- The backend's CORS allows the Vite origin **`http://localhost:5173`** (and `127.0.0.1:5173`).
- **Polling:**
  - every 4 s for the board: `/api/tickets`, `/api/cash`, `/api/approvals`, `/api/drafts`, `/api/health`
  - every 1.2 s while a run is active: `/api/events?after=N` (incremental, newest only) and `/api/runs/{id}`
- **Start:**
  1. Run the backend from `backend/` with `uvicorn main:app --reload --port 8000`.
  2. Run the board from `frontend/` with `npm install` (first time), then `npm run dev`. Vite opens `http://localhost:5173` in your browser.
