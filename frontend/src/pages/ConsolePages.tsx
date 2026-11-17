import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  ChevronRight,
  CircleAlert,
  Clock3,
  Copy,
  Database,
  Plus,
  RefreshCw,
  Scale,
  ShieldCheck,
  Wallet,
} from "lucide-react";
import { toast } from "sonner";
import {
  ActivityTimeline,
  ChartPanel,
  ConfirmationDialog,
  DataTable,
  EmptyState,
  ErrorState,
  FilterBar,
  LoadingState,
  MetricCard,
  PageHeader,
  StatusBadge,
} from "../components/ui";
import {
  accountIds,
  accountNames,
  balancesFor,
  money,
  type Entry,
  type Health,
} from "../model";
import { destinations } from "../components/AppShell";

interface Props {
  entries: Entry[];
  post: (entry: Entry) => void;
  reset: () => void;
  health: Health;
  persona: string;
  setPersona: (value: string) => void;
}
export function ConsolePages({
  entries,
  post,
  reset,
  health,
  persona,
  setPersona,
}: Props) {
  const { section = "" } = useParams();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All statuses");
  const [period, setPeriod] = useState("All activity");
  const [transferOpen, setTransferOpen] = useState(false);
  const [selected, setSelected] = useState<Entry | null>(null);
  const [resetOpen, setResetOpen] = useState(false);
  const [source, setSource] = useState(0);
  const balances = balancesFor(entries);
  const visible = entries.filter((entry) =>
    (entry.description + entry.id + accountNames[entry.source])
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  const filtered =
    period === "Latest day"
      ? visible.filter(
          (entry) => entry.time.slice(0, 10) === entries[0]?.time.slice(0, 10),
        )
      : visible;
  const totalVolume = filtered.reduce((sum, entry) => sum + entry.amount, 0);
  const canTransfer = persona === "Operator demo";
  const title = destinations.find((item) => item.slug === section)?.label;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem(
      "amount",
    ) as HTMLInputElement;
    const cents = Math.round(Number(input.value) * 100);
    if (!Number.isSafeInteger(cents) || cents < 1 || cents > balances[source]) {
      input.setCustomValidity("Enter an amount within the available balance.");
      input.reportValidity();
      return;
    }
    post({
      amount: cents,
      source,
      time: new Date().toISOString(),
      key: crypto.randomUUID(),
      id: "LO-" + crypto.randomUUID().slice(0, 8).toUpperCase(),
      description: "Internal liquidity allocation",
    });
    setTransferOpen(false);
  }
  async function copy(key: string) {
    try {
      await navigator.clipboard.writeText(key);
      toast.success("Idempotency key copied");
    } catch {
      toast.error("Clipboard unavailable");
    }
  }
  function exportJournal() {
    const rows = [
      "Reference,Description,Amount USD,Source,Destination,Timestamp",
      ...filtered.map((entry) =>
        [
          entry.id,
          entry.description,
          (entry.amount / 100).toFixed(2),
          accountIds[entry.source],
          accountIds[1 - entry.source],
          entry.time,
        ].join(","),
      ),
    ];
    const link = document.createElement("a");
    link.href = URL.createObjectURL(
      new Blob([rows.join("\n")], { type: "text/csv" }),
    );
    link.download = "ledgerops-demo-journal.csv";
    link.click();
    URL.revokeObjectURL(link.href);
  }
  const newTransfer = (
    <button
      className="button primary"
      onClick={() => setTransferOpen(true)}
      disabled={!canTransfer}
    >
      <Plus size={16} />
      Simulate transfer
    </button>
  );
  const journal = (
    <section className="panel">
      <div className="panel-heading">
        <h2>
          {section === "ledger" ? "Balanced journal" : "Recent transactions"}
        </h2>
        <span className="subtle">Session demo data</span>
      </div>
      {section !== "" && (
        <FilterBar
          value={search}
          setValue={setSearch}
          status={status}
          setStatus={setStatus}
        />
      )}
      <DataTable entries={filtered} select={setSelected} />
      {section === "" && (
        <Link className="panel-footer-link" to="/console/transfers">
          View all transactions <ArrowRight size={14} />
        </Link>
      )}
    </section>
  );
  const healthPanel = (
    <section className="panel health-panel">
      <div className="panel-heading">
        <h2>Service health</h2>
        <Link className="text-link" to="/console/health">
          Details <ArrowUpRight size={14} />
        </Link>
      </div>
      <div className="health-summary">
        <span className="health-orbit">
          <ShieldCheck size={22} />
        </span>
        <div>
          <strong>
            {health.state === "Operational"
              ? "API ready to serve"
              : "API " + health.state.toLowerCase()}
          </strong>
          <p>Live FastAPI readiness check</p>
        </div>
        <StatusBadge
          tone={health.state === "Operational" ? "success" : "warning"}
        >
          {health.state}
        </StatusBadge>
      </div>
      <div className="service-details">
        <span>Last checked</span>
        <span className="numeric">{health.checked || "Checking…"}</span>
      </div>
    </section>
  );
  let content;
  if (!title)
    content = (
      <EmptyState title="Page not found">
        Choose a destination from the sidebar.
      </EmptyState>
    );
  else if (section === "")
    content = (
      <>
        <PageHeader
          title="Workspace overview"
          description="A considered view of your financial operations."
          actions={
            <div className="header-actions">
              <label className="sr-only" htmlFor="period">
                Activity period
              </label>
              <select
                id="period"
                value={period}
                onChange={(event) => setPeriod(event.target.value)}
              >
                <option>All activity</option>
                <option>Latest day</option>
              </select>
              {newTransfer}
            </div>
          }
        />
        <div className="demo-notice">
          <span className="tiny-square" />
          <strong>Sandbox workspace</strong>
          <span>
            Financial data is synthetic and resets on refresh. Service readiness
            is live.
          </span>
        </div>
        <div className="financial-summary">
          <div className="wealth-summary">
            <div>
              <span className="eyebrow">Total simulated balance</span>
              <div className="wealth-amount numeric">
                {money(balances[0] + balances[1])}
                <span>USD</span>
              </div>
              <p>
                <Scale size={15} /> Equal debits and credits across{" "}
                {entries.length} transfers
              </p>
            </div>
            <Link to="/console/accounts">
              View accounts <ArrowUpRight size={18} />
            </Link>
          </div>
          <div className="summary-side">
            <MetricCard
              label="Synthetic accounts"
              value="02"
              detail="Operating & settlement"
            />
            <MetricCard
              label="Transfer volume"
              value={money(totalVolume)}
              detail={
                filtered.length + " demo transfers · " + period.toLowerCase()
              }
            />
          </div>
        </div>
        <div className="charts-grid">
          <ChartPanel
            title="Transaction volume"
            description="Demo journal · USD"
          >
            <div className="chart-total numeric">
              {money(totalVolume)}
              <small>Recorded activity</small>
            </div>
            <div
              className="bar-chart"
              role="img"
              aria-label={filtered
                .map((entry) => entry.id + " " + money(entry.amount))
                .join(", ")}
            >
              {filtered
                .slice(0, 12)
                .reverse()
                .map((entry, index) => (
                  <div className="bar-column" key={entry.key}>
                    <div className="bar-track">
                      <div
                        className={index % 2 ? "bar champagne" : "bar"}
                        style={{
                          height:
                            Math.max(
                              4,
                              (entry.amount /
                                Math.max(
                                  ...filtered.map((item) => item.amount),
                                )) *
                                100,
                            ) + "%",
                        }}
                        title={money(entry.amount)}
                      />
                    </div>
                    <span>
                      {new Date(entry.time).toLocaleDateString("en-GB", {
                        month: "short",
                        day: "numeric",
                      })}
                    </span>
                  </div>
                ))}
            </div>
          </ChartPanel>
          <ChartPanel title="Transaction status" description="Demo journal">
            <div className="distribution">
              <div className="donut">
                <strong className="numeric">{filtered.length}</strong>
                <small>transfers</small>
              </div>
              <div className="distribution-labels">
                <div>
                  <span className="legend-dot" />
                  Recorded <b>{filtered.length}</b>
                </div>
                <p>
                  Every displayed transfer belongs to the browser simulation.
                </p>
                <Link className="text-link" to="/console/ledger">
                  Inspect the journal <ArrowUpRight size={14} />
                </Link>
              </div>
            </div>
          </ChartPanel>
        </div>
        <div className="overview-bottom">
          <div>
            {journal}
            <section className="panel activity-panel">
              <div className="panel-heading">
                <h2>Recent session activity</h2>
                <StatusBadge>Demo</StatusBadge>
              </div>
              <ActivityTimeline entries={entries} />
            </section>
          </div>
          <div>
            {healthPanel}
            <section className="panel attention-panel">
              <div className="panel-heading">
                <h2>Operations workbench</h2>
                <Clock3 size={17} />
              </div>
              <Link to="/console/approvals">
                <span className="attention-icon">
                  <ShieldCheck size={18} />
                </span>
                <div>
                  <strong>Pending approvals</strong>
                  <small>Awaiting workflow integration</small>
                </div>
                <ChevronRight size={15} />
              </Link>
              <Link to="/console/exceptions">
                <span className="attention-icon">
                  <CircleAlert size={18} />
                </span>
                <div>
                  <strong>Exceptions</strong>
                  <small>Awaiting workflow integration</small>
                </div>
                <ChevronRight size={15} />
              </Link>
              <div className="small-note">
                Unavailable queues have no reported count.
              </div>
            </section>
          </div>
        </div>
      </>
    );
  else if (section === "accounts")
    content = (
      <>
        <PageHeader
          title="Accounts"
          description="Two synthetic accounts in the browser sandbox."
        />
        <div className="account-grid">
          {accountNames.map((name, index) => (
            <article className="panel account-detail" key={name}>
              <Wallet size={25} />
              <StatusBadge>Demo</StatusBadge>
              <h2>{name}</h2>
              <code>{accountIds[index]}</code>
              <strong className="account-amount numeric">
                {money(balances[index])}
              </strong>
              <p>USD · Synthetic workspace account</p>
              <button
                className="button secondary"
                onClick={() => {
                  setSource(index);
                  setTransferOpen(true);
                }}
                disabled={!canTransfer}
              >
                Simulate transfer <ArrowUpRight size={15} />
              </button>
            </article>
          ))}
        </div>
        <p className="small-note">
          Account lifecycle and customer ownership require the future backend
          account API.
        </p>
      </>
    );
  else if (section === "transfers" || section === "ledger")
    content = (
      <>
        <PageHeader
          title={title}
          description="Session-only transfers with balanced debit and credit postings."
          actions={
            <div className="header-actions">
              <button className="button secondary" onClick={exportJournal}>
                <ArrowDownToLine size={16} />
                Export demo CSV
              </button>
              {newTransfer}
            </div>
          }
        />
        {!canTransfer && (
          <div className="demo-notice">
            Auditor preview · Transfer creation is unavailable for this demo
            persona.
          </div>
        )}
        {journal}
      </>
    );
  else if (section === "health" || section === "infrastructure")
    content = (
      <>
        <PageHeader
          title={title}
          description="Live status from FastAPI. Unconfigured services and measurements remain unavailable."
          actions={
            <button className="button secondary" onClick={health.refresh}>
              <RefreshCw size={15} />
              Refresh status
            </button>
          }
        />
        {health.state === "Checking" ? (
          <LoadingState />
        ) : health.state === "Unavailable" ? (
          <ErrorState retry={health.refresh} />
        ) : (
          <>
            {healthPanel}
            <div className="account-grid">
              {Object.entries(health.checks).map(([name, value]) => {
                const isDb = name === "database";
                // Branch explicitly on undefined so a missing database key
                // shows "Not configured" rather than falling back to "Passing".
                const configured = value !== undefined;
                const tone = !configured
                  ? "warning"
                  : value === "ok"
                    ? "success"
                    : "warning";
                const label = !configured
                  ? "Not configured"
                  : value === "ok"
                    ? "Passing"
                    : "Failing";
                return (
                  <article key={name} className="panel account-detail">
                    <Database size={23} />
                    <h2>
                      {isDb ? "Database & schema" : "Application lifecycle"}
                    </h2>
                    <StatusBadge tone={tone}>{label}</StatusBadge>
                    <p>
                      Source · GET /health/ready
                      <br />
                      Last checked · {health.checked}
                    </p>
                  </article>
                );
              })}
            </div>
          </>
        )}
        <section className="panel">
          <EmptyState title="Additional telemetry unavailable">
            Latency percentiles, resource utilization, worker status, and
            deployment telemetry will appear after instrumentation is connected.
          </EmptyState>
        </section>
      </>
    );
  else if (section === "settings")
    content = (
      <>
        <PageHeader
          title="Workspace settings"
          description="Preferences for the local demo experience."
        />
        <section className="panel settings-panel">
          <h2>Demo persona</h2>
          <p>
            This changes the UI preview. Authentication and server authorization
            require PR 4 integration.
          </p>
          <label>
            Persona
            <select
              value={persona}
              onChange={(event) => setPersona(event.target.value)}
            >
              <option>Operator demo</option>
              <option>Auditor demo</option>
            </select>
          </label>
          <hr />
          <h2>Reset session data</h2>
          <p>Restore the original synthetic accounts and transfer journal.</p>
          <button
            className="button secondary"
            onClick={() => setResetOpen(true)}
          >
            Reset demo data
          </button>
        </section>
      </>
    );
  else if (section === "users")
    content = (
      <>
        <PageHeader
          title={title}
          description="Identity and access administration."
        />
        <section className="panel">
          <EmptyState title="Authentication required">
            User administration requires a backend authenticated session and
            administrator permission. This public demo has no authenticated
            operator.
          </EmptyState>
        </section>
      </>
    );
  else
    content = (
      <>
        <PageHeader
          title={title}
          description={
            section === "audit"
              ? "Governance records with actor and request context."
              : "A dedicated workspace for controlled financial operations."
          }
        />
        <section className="panel">
          <EmptyState
            title={
              section === "audit"
                ? "Audit integration unavailable"
                : "Workflow integration unavailable"
            }
          >
            The {title.toLowerCase()} service is awaiting backend integration.{" "}
            {section === "audit"
              ? "The demo session activity is available on Overview."
              : "No operational records or counts are reported for this queue."}
          </EmptyState>
        </section>
      </>
    );
  return (
    <>
      {content}
      <ConfirmationDialog
        open={transferOpen}
        close={() => setTransferOpen(false)}
        title="Simulate a transfer"
      >
        <form onSubmit={submit}>
          <p>
            Move synthetic funds between your two demo accounts. This updates
            the current browser session.
          </p>
          <label>
            From account
            <select
              value={source}
              onChange={(event) => setSource(Number(event.target.value))}
            >
              {accountNames.map((name, index) => (
                <option key={name} value={index}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <p>
            Available{" "}
            <strong className="numeric">{money(balances[source])}</strong>
          </p>
          <div className="transfer-destination">
            <ArrowRight size={15} />
            To {accountNames[1 - source]}
          </div>
          <label>
            Amount · USD
            <input
              name="amount"
              type="number"
              min=".01"
              max={balances[source] / 100}
              step=".01"
              required
              defaultValue="250.00"
              onInput={(event) => event.currentTarget.setCustomValidity("")}
            />
          </label>
          <div className="dialog-actions">
            <button
              type="button"
              className="button secondary"
              onClick={() => setTransferOpen(false)}
            >
              Cancel
            </button>
            <button className="button primary">Post simulated transfer</button>
          </div>
        </form>
      </ConfirmationDialog>
      <ConfirmationDialog
        open={!!selected}
        close={() => setSelected(null)}
        title="Journal entry"
      >
        {selected && (
          <div className="entry-detail">
            <StatusBadge tone="success">Recorded · Demo</StatusBadge>
            <h3 className="numeric">{selected.id}</h3>
            <p>{selected.description}</p>
            <dl>
              <dt>Debit · {accountNames[1 - selected.source]}</dt>
              <dd>{money(selected.amount)}</dd>
              <dt>Credit · {accountNames[selected.source]}</dt>
              <dd>{money(selected.amount)}</dd>
              <dt>Timestamp</dt>
              <dd>{new Date(selected.time).toISOString()}</dd>
            </dl>
            <label>
              Idempotency key<code>{selected.key}</code>
            </label>
            <div className="dialog-actions">
              <button
                className="button secondary"
                onClick={() => copy(selected.key)}
              >
                <Copy size={15} />
                Copy key
              </button>
              <button className="button primary" onClick={() => post(selected)}>
                Replay request
              </button>
            </div>
            <p className="small-note">
              Replay detection applies to this browser session.
            </p>
          </div>
        )}
      </ConfirmationDialog>
      <ConfirmationDialog
        open={resetOpen}
        close={() => setResetOpen(false)}
        title="Reset demo data?"
      >
        <p>
          Session transfers will be replaced with the original synthetic
          journal.
        </p>
        <div className="dialog-actions">
          <button
            className="button secondary"
            onClick={() => setResetOpen(false)}
          >
            Cancel
          </button>
          <button
            className="button primary"
            onClick={() => {
              reset();
              setResetOpen(false);
              toast.success("Demo data restored");
            }}
          >
            Reset demo data
          </button>
        </div>
      </ConfirmationDialog>
    </>
  );
}
