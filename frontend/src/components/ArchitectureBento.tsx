import { Activity, GitBranch, KeyRound, Scale } from 'lucide-react';

export function ArchitectureBento() {
  return <section id="architecture" className="wrap" aria-labelledby="architecture-title">
    <h2 id="architecture-title">Financial operations architecture</h2>
    <p>How LedgerOps balances simulated transfers and monitors the services behind them.</p>
    <div className="architecture-grid">
      <article><Scale aria-hidden="true"/><h3>Immutable Double-Entry Ledger</h3>
        <p>The sandbox posts equal debits and credits in integer cents. An immutable journal and concurrency controls are database design targets.</p>
        <code>Design target · ACID • SUM(DR) == SUM(CR)</code></article>
      <article><KeyRound aria-hidden="true"/><h3>Idempotent Transfers</h3>
        <p>Replay an accepted key in this browser session. The balances stay unchanged. Server-side replay protection is planned.</p></article>
      <article><GitBranch aria-hidden="true"/><h3>Strangler Fig Migration</h3>
        <p>FastAPI services incrementally replace the Flask and SQLite expense tracker, preserved under <code>legacy/expense-tracker/</code>.</p>
        <a href="https://github.com/darshsoam07/Expense-Tracker-with-Insights/blob/main/docs/architecture/adr/0006-strangler-migration.md">Read ADR-0006 ↗</a></article>
      <article><Activity aria-hidden="true"/><h3>Structured Telemetry &amp; Health Probes</h3>
        <p>JSON logs carry request IDs. Separate liveness and readiness probes report service state, and CI checks import boundaries.</p>
        <code>SRE · GET /health/ready</code></article>
    </div>
    <footer><strong>Phase 1 · FastAPI + React</strong> LedgerOps uses synthetic customers and simulated funds only. No connection to real banking rails or regulatory certification.</footer>
  </section>;
}
