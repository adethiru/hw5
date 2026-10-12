# Campus Customs · Ops Desk (frontend)

React + Vite + TypeScript dashboard for the Campus Customs agent team.

```bash
# 1) backend (from Homework 5/backend)
uvicorn main:app --reload --port 8000

# 2) dashboard (from Homework 5/frontend)
npm install      # first time only
npm run dev      # opens http://localhost:5173
```

The page calls the backend at `http://localhost:8000` (see `src/api.ts`; override with `VITE_API_BASE` in `frontend/.env`). The backend allows the `http://localhost:5173` origin via CORS.

What you can do:

- Pick a ticket and run the agent team on it.
- Watch each agent work live: the roster, every tool call and every hand-off.
- Read the run summary.
- Approve or reject payments, purchase orders and price overrides. The checking balance drops after an approved payment.
- Reset the database.

Design notes: see `../output/design.md`.
