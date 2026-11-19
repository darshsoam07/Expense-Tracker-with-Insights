import { useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import {
  api,
  type Account,
  type Hold,
  type HoldEvent,
  type User,
} from "../api";
import { ConfirmationDialog } from "../components/ui";

export function AccountHolds({
  account,
  user,
  refresh,
}: {
  account: Account;
  user: User;
  refresh: () => void;
}) {
  const writable =
    account.status === "active" && account.membership_role !== "viewer";
  const [offset, setOffset] = useState(0);
  const [selected, select] = useState("");
  const [eventOffset, setEventOffset] = useState(0);
  const [rows, setRows] = useState<Hold[]>([]);
  const [events, setEvents] = useState<HoldEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [action, setAction] = useState<"create" | Hold | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const attempt = useRef<{ body: string; key: string } | null>(null);
  useEffect(() => {
    let current = true;
    setLoading(true);
    setError("");
    async function load() {
      const list = await api.holds(account.id, offset);
      const history = selected
        ? (await api.hold(selected, eventOffset)).events
        : [];
      if (current) {
        setRows(list);
        setEvents(history);
      }
    }
    load()
      .catch((e) => {
        if (current) setError(e.message);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [account.id, offset, selected, eventOffset, retry]);
  function open(value: "create" | Hold) {
    setMessage("");
    setAction(value);
  }
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!action || pending.current) return;
    const data = new FormData(e.currentTarget);
    const amount = String(data.get("amount") ?? "");
    const expires = String(data.get("expires") ?? "");
    const body = {
      currency: "INR" as const,
      amount,
      reason: String(data.get("reason") ?? "").trim(),
      expires_at: expires ? new Date(expires).toISOString() : null,
      business_reference: String(data.get("reference") ?? "").trim() || null,
    };
    const target = action === "create" ? account.id : action.id;
    const fingerprint = JSON.stringify([
      target,
      action === "create" ? "create" : "release",
      body,
    ]);
    if (attempt.current?.body !== fingerprint)
      attempt.current = { body: fingerprint, key: crypto.randomUUID() };
    pending.current = true;
    setBusy(true);
    setMessage("");
    try {
      const receipt =
        action === "create"
          ? await api.createHold(target, body, attempt.current.key)
          : await api.releaseHold(target, amount || null, attempt.current.key);
      toast.success("Hold " + receipt.kind.replaceAll("_", " "), {
        description: receipt.hold_id,
      });
      attempt.current = null;
      setAction(null);
      refresh();
    } catch (e) {
      setMessage(
        e instanceof Error ? e.message : "Hold command could not be confirmed.",
      );
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <section aria-label="Account holds">
      <h3>Account holds</h3>
      {writable && user.permissions.includes("holds.create") && (
        <button className="button primary" onClick={() => open("create")}>
          Reserve funds
        </button>
      )}
      {loading ? (
        <p role="status">Loading holds…</p>
      ) : error ? (
        <p role="alert">
          {error} <button onClick={() => setRetry((n) => n + 1)}>Retry</button>
        </p>
      ) : (
        <>
          {!rows.length && <p>No holds on this page.</p>}
          {rows.map((h) => (
            <article key={h.id}>
              <strong>{h.reason}</strong>
              <p>
                {h.status.replaceAll("_", " ")} · Remaining{" "}
                <span className="numeric">
                  {h.currency} {h.remaining}
                </span>{" "}
                of{" "}
                <span className="numeric">
                  {h.currency} {h.original_amount}
                </span>
              </p>
              {h.expires_at && (
                <p>
                  Expires <time>{h.expires_at}</time>
                </p>
              )}
              <button
                onClick={() => {
                  select(selected === h.id ? "" : h.id);
                  setEventOffset(0);
                }}
              >
                History for {h.reason}
              </button>
              {writable &&
                user.permissions.includes("holds.release") &&
                (account.membership_role !== "member" ||
                  h.creator === user.id) &&
                ["active", "partially_released"].includes(h.status) && (
                  <button onClick={() => open(h)}>Release funds</button>
                )}
              {selected === h.id && (
                <section aria-label="Hold history">
                  {events.map((v) => (
                    <p key={v.id}>
                      <time>{v.occurred_at}</time> ·{" "}
                      {v.kind.replaceAll("_", " ")} ·{" "}
                      <span className="numeric">
                        {v.currency} {v.amount}
                      </span>
                      {v.journal_id && <code>{v.journal_id}</code>}
                    </p>
                  ))}
                  <button
                    disabled={!eventOffset}
                    onClick={() => setEventOffset((n) => n - 10)}
                  >
                    Previous events
                  </button>
                  <button
                    disabled={events.length < 10}
                    onClick={() => setEventOffset((n) => n + 10)}
                  >
                    Next events
                  </button>
                </section>
              )}
            </article>
          ))}
          <button
            disabled={!offset}
            onClick={() => {
              select("");
              setOffset((n) => n - 10);
            }}
          >
            Previous holds
          </button>
          <button
            disabled={rows.length < 10}
            onClick={() => {
              select("");
              setOffset((n) => n + 10);
            }}
          >
            Next holds
          </button>
        </>
      )}
      <ConfirmationDialog
        open={action !== null}
        close={() => {
          if (!pending.current) setAction(null);
        }}
        title={action === "create" ? "Reserve funds" : "Release reserved funds"}
      >
        {action && (
          <form onSubmit={submit}>
            <fieldset disabled={busy}>
              {message && <p role="alert">{message}</p>}
              {action !== "create" && (
                <p>
                  Remaining{" "}
                  <span className="numeric">
                    {action.currency} {action.remaining}
                  </span>
                  . Leave amount empty to release the full remainder.
                </p>
              )}
              <label>
                Amount · INR
                <input
                  name="amount"
                  inputMode="decimal"
                  required={action === "create"}
                  pattern="(0|[1-9][0-9]{0,15})([.][0-9]{1,2})?"
                />
              </label>
              {action === "create" && (
                <>
                  <label>
                    Reason
                    <input name="reason" required maxLength={256} />
                  </label>
                  <label>
                    Business reference (optional)
                    <input name="reference" maxLength={128} />
                  </label>
                  <label>
                    Expires at (local time, optional)
                    <input name="expires" type="datetime-local" />
                  </label>
                </>
              )}
              <button className="button primary" disabled={busy}>
                {busy
                  ? "Submitting…"
                  : action === "create"
                    ? "Confirm reservation"
                    : "Confirm release"}
              </button>
            </fieldset>
          </form>
        )}
      </ConfirmationDialog>
    </section>
  );
}
