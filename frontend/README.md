# LedgerOps frontend

React, TypeScript, Vite and Tailwind power two experiences: the public website at / and the operations workspace at /console.

## Run and verify

From this worktree's root, in PowerShell:

~~~powershell
npm ci --prefix frontend
npm run dev --prefix frontend -- --host 127.0.0.1
npm run typecheck --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
~~~

Vite proxies /health to FastAPI on port 8000. VITE_API_BASE_URL can target a configured API directly, provided its CORS policy permits the browser origin.

## Demo boundaries

Accounts, transfers, journal entries and charts share a synthetic, browser-memory dataset. Data resets when the console is reloaded or left. There is no durable financial posting. The transfer dialog, copy key, replay detection, filtered CSV export and reset confirmation work within this dataset.

All navigation destinations have real URLs. Pending backend workflows display unavailable states. Users & Access explains the authentication requirement. The Operator/Auditor setting previews UI permissions only. It cannot authorize API requests.

The readiness indicator and Service Health page call the real FastAPI health endpoint. Metrics without an instrumentation source remain unavailable.

For layout stress testing, append ?data=worst to a console route during development. It supplies long account identifiers, an unbroken settlement description and very large safe-integer balances through the normal data boundary. This fixture is excluded from production behavior.

## Component verification

Vitest and Testing Library cover both transfer directions, preservation of the combined balance, transfer creation across navigation, replay detection, filtered empty states, auditor controls, and health failures with retry feedback. The API response is stubbed in component tests. Browser verification uses the real local readiness route.

The approved palette is in ../design-system/ledgerops/tokens.css. Its documentation is maintained alongside the implementation.
