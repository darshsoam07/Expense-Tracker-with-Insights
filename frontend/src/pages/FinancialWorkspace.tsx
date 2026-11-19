import { useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import {
  api,
  type Account,
  type Posting,
  type Transfer,
  type TransferCommand,
} from "../api";
import { useAuth } from "../context/AuthContext";
import { ConfirmationDialog, PageHeader } from "../components/ui";

export function FinancialWorkspace({ section }: { section: string }) {
  const { user } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selected, select] = useState("");
  const [detail, setDetail] = useState<Account | null>(null);
  const [postings, setPostings] = useState<Posting[]>([]);
  const [history, setHistory] = useState<Transfer[]>([]);
  const [offset, setOffset] = useState(0);
  const [revision, refresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const attempt = useRef<{ payload: string; key: string } | null>(null);
  const [command, setCommand] = useState<TransferCommand>({
    source_id: "",
    destination_id: "",
    currency: "INR",
    amount: "",
    description: "",
  });
  function edit(field: keyof TransferCommand, value: string) {
    attempt.current = null;
    setCommand((previous) => ({ ...previous, [field]: value }));
  }
  useEffect(() => {
    let current = true;
    setLoading(true);
    setError("");
    async function load() {
      const list = await api.accounts();
      const accountId = selected || list[0]?.id;
      const detail =
        section === "accounts" && selected ? await api.account(selected) : null;
      const activity =
        section === "ledger" && accountId
          ? await api.ledger(accountId, offset)
          : [];
      const transfers =
        section === "transfers" ? await api.transfers(offset) : [];
      if (current) {
        setDetail(detail);
        setAccounts(list);
        setPostings(activity);
        setHistory(transfers);
      }
    }
    load()
      .catch((e: Error) => {
        if (current) setError(e.message);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [section, selected, offset, revision]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending.current || command.source_id === command.destination_id) return;
    const payload = JSON.stringify(command);
    if (attempt.current?.payload !== payload)
      attempt.current = { payload, key: crypto.randomUUID() };
    pending.current = true;
    setBusy(true);
    try {
      const transfer = await api.createTransfer(command, attempt.current.key);
      toast.success("Internal transfer posted", {
        description: transfer.journal_reference,
      });
      attempt.current = null;
      setOpen(false);
      setCommand((previous) => ({ ...previous, amount: "", description: "" }));
      setOffset(0);
      refresh((previous) => previous + 1);
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : "Transfer could not be confirmed.",
      );
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  const options = accounts
    .filter((a) => a.status === "active")
    .map((a) => (
      <option value={a.id} key={a.id}>
        {a.customer_name} · {a.reference}
      </option>
    ));
  return (
    <>
      <PageHeader
        title={
          {
            accounts: "Accounts",
            ledger: "Ledger Explorer",
            transfers: "Internal transfers",
          }[section] ?? "Accounts"
        }
        description="Synthetic accounts and simulated INR funds."
      />
      {loading ? (
        <p role="status">Loading financial records…</p>
      ) : error ? (
        <div role="alert">
          {error} <button onClick={() => refresh(revision + 1)}>Retry</button>
        </div>
      ) : (
        <>
          {detail && (
            <section className="panel">
              <h2>Account detail</h2>
              <code>{detail.reference}</code>
              <p>
                {detail.customer_name} · {detail.status}
              </p>
              <p>
                Ledger balance {detail.currency} {detail.ledger_balance}
              </p>
              <p>
                Available balance {detail.currency} {detail.available_balance}
              </p>
              <button onClick={() => select("")}>Close detail</button>
            </section>
          )}
          {section === "accounts" && (
            <div className="account-grid">
              {accounts.map((a) => (
                <article className="panel account-detail" key={a.id}>
                  <h2>{a.customer_name}</h2>
                  <code>{a.reference}</code>
                  <p>{a.status}</p>
                  <p>
                    Ledger balance{" "}
                    <strong className="numeric">
                      {a.currency} {a.ledger_balance}
                    </strong>
                  </p>
                  <p>
                    Available balance{" "}
                    <strong className="numeric">
                      {a.currency} {a.available_balance}
                    </strong>
                  </p>
                  <button onClick={() => select(a.id)}>View account</button>
                </article>
              ))}
            </div>
          )}
          {!accounts.length && <p>No accounts available to this user.</p>}
          {section === "ledger" && accounts.length > 0 && (
            <section className="panel">
              <label>
                Account{" "}
                <select
                  value={selected || accounts[0].id}
                  onChange={(e) => {
                    select(e.target.value);
                    setOffset(0);
                  }}
                >
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.customer_name} · {a.reference}
                    </option>
                  ))}
                </select>
              </label>
              {postings.map((p) => (
                <article key={p.id}>
                  <code>{p.reference}</code>
                  <p>
                    {p.description} · {p.direction} · {p.currency} {p.amount}
                  </p>
                  <time>{p.posted_at}</time>
                </article>
              ))}
              {!postings.length && <p>No posted activity on this page.</p>}
            </section>
          )}
          {section === "transfers" && (
            <section className="panel">
              <h2>Transfer history</h2>
              {user?.permissions.includes("transfers.create") && (
                <button
                  className="button primary"
                  disabled={options.length < 2}
                  onClick={() => setOpen(true)}
                >
                  New internal transfer
                </button>
              )}
              {history.map((t) => (
                <article key={t.id}>
                  <code>{t.journal_reference}</code>
                  <p>
                    {t.status} · {t.currency} {t.amount}
                  </p>
                  <time>{t.created_at}</time>
                </article>
              ))}
              {!history.length && <p>No posted transfers on this page.</p>}
            </section>
          )}
          {section !== "accounts" && (
            <nav aria-label="Activity pages">
              <button disabled={!offset} onClick={() => setOffset(offset - 25)}>
                Previous
              </button>
              <button
                disabled={
                  (section === "ledger" ? postings : history).length < 25
                }
                onClick={() => setOffset(offset + 25)}
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
      <ConfirmationDialog
        open={open}
        close={() => {
          if (!pending.current) setOpen(false);
        }}
        title="Internal transfer"
      >
        <form onSubmit={submit}>
          <fieldset disabled={busy}>
            <label>
              Source account
              <select
                required
                value={command.source_id}
                onChange={(e) => edit("source_id", e.target.value)}
              >
                <option value="">Choose account</option>
                {options}
              </select>
            </label>
            <label>
              Destination account
              <select
                required
                value={command.destination_id}
                onChange={(e) => edit("destination_id", e.target.value)}
              >
                <option value="">Choose account</option>
                {options.filter((o) => o.key !== command.source_id)}
              </select>
            </label>
            <label>
              Amount · INR
              <input
                required
                inputMode="decimal"
                pattern="(0|[1-9][0-9]{0,15})([.][0-9]{1,2})?"
                value={command.amount}
                onChange={(e) => edit("amount", e.target.value)}
              />
            </label>
            <label>
              Description
              <input
                maxLength={256}
                value={command.description}
                onChange={(e) => edit("description", e.target.value)}
              />
            </label>
            <button
              className="button primary"
              disabled={busy || command.source_id === command.destination_id}
            >
              {busy ? "Posting…" : "Post internal transfer"}
            </button>
          </fieldset>
        </form>
      </ConfirmationDialog>
    </>
  );
}
