import { useEffect, useRef, type ReactNode } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Check,
  CircleAlert,
  Layers,
  LoaderCircle,
} from "lucide-react";
import { Link } from "react-router-dom";
import { money, accountNames, type Entry } from "../model";

export function Brand() {
  return (
    <Link className="brand" to="/" aria-label="LedgerOps home">
      <span className="brand-mark">
        <Layers size={22} />
      </span>
      LedgerOps<span className="brand-dot">.</span>
    </Link>
  );
}
export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "success" | "warning" | "neutral";
}) {
  return (
    <span className={"status-badge " + tone}>
      <span aria-hidden="true" />
      {children}
    </span>
  );
}
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <div className="eyebrow">{eyebrow ?? "Workspace / Sandbox"}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions}
    </div>
  );
}
export function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <article className="metric">
      <span>{label}</span>
      <strong className="numeric">{value}</strong>
      <small>{detail}</small>
    </article>
  );
}
export function ChartPanel({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
        <span className="subtle">{description}</span>
      </div>
      {children}
    </section>
  );
}
export function EmptyState({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty-state">
      <Layers size={26} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function LoadingState() {
  return (
    <div className="empty-state" role="status">
      <LoaderCircle />
      <p>Checking service readiness…</p>
    </div>
  );
}
export function ErrorState({
  retry,
  title = "Service unavailable",
  children = "A readiness response could not be retrieved.",
}: {
  retry: () => void;
  title?: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty-state" role="alert">
      <CircleAlert />
      <h3>{title}</h3>
      <p>{children}</p>
      <button className="button secondary" onClick={retry}>
        Try again
      </button>
    </div>
  );
}
export function FilterBar({
  value,
  setValue,
  status,
  setStatus,
}: {
  value: string;
  setValue: (value: string) => void;
  status: string;
  setStatus: (value: string) => void;
}) {
  return (
    <div className="filter-bar">
      <label className="search-label">
        Search transactions
        <input
          type="search"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Search reference or description"
        />
      </label>
      <label>
        Status
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
        >
          <option>All statuses</option>
          <option>Recorded</option>
        </select>
      </label>
    </div>
  );
}
export function TransactionRow({
  entry,
  select,
}: {
  entry: Entry;
  select: (entry: Entry) => void;
}) {
  return (
    <tr>
      <td>
        <button className="table-reference" onClick={() => select(entry)}>
          <span className="transaction-icon">
            {entry.source === 0 ? (
              <ArrowUpRight size={17} />
            ) : (
              <ArrowDownLeft size={17} />
            )}
          </span>
          <span>
            <strong>{entry.description}</strong>
            <small className="numeric">{entry.id}</small>
          </span>
        </button>
      </td>
      <td>
        {accountNames[entry.source]}
        <small>Internal transfer</small>
      </td>
      <td className="numeric amount">{money(entry.amount)}</td>
      <td>
        <StatusBadge tone="success">Recorded</StatusBadge>
      </td>
      <td className="numeric">
        {new Date(entry.time).toLocaleDateString("en-GB", {
          day: "2-digit",
          month: "short",
        })}
      </td>
    </tr>
  );
}
export function DataTable({
  entries,
  select,
}: {
  entries: Entry[];
  select: (entry: Entry) => void;
}) {
  return entries.length ? (
    <div
      className="table-scroll"
      role="region"
      aria-label="Transactions"
      tabIndex={0}
    >
      <table>
        <thead>
          <tr>
            <th>Transaction</th>
            <th>From account</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Date</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <TransactionRow key={entry.key} entry={entry} select={select} />
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <EmptyState title="No matching transactions">
      Try another reference or clear your search.
    </EmptyState>
  );
}
export function ActivityTimeline({ entries }: { entries: Entry[] }) {
  return (
    <ol className="activity">
      {entries.slice(0, 4).map((entry) => (
        <li key={entry.key}>
          <span className="activity-icon">
            <Check size={13} />
          </span>
          <div>
            <strong>Simulated transfer recorded</strong>
            <p>
              {entry.id} · {money(entry.amount)}
            </p>
          </div>
          <time>
            {new Date(entry.time).toLocaleTimeString("en-GB", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </time>
        </li>
      ))}
    </ol>
  );
}
export function ConfirmationDialog({
  open,
  close,
  title,
  children,
}: {
  open: boolean;
  close: () => void;
  title: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (open && !ref.current?.open) ref.current?.showModal();
    if (!open) ref.current?.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onClose={close}
      aria-labelledby="dialog-title"
    >
      <div className="dialog-heading">
        <h2 id="dialog-title">{title}</h2>
        <button onClick={close} aria-label="Close dialog">
          ×
        </button>
      </div>
      {children}
    </dialog>
  );
}
