import { useEffect, useState } from "react";
import { api, type Approval } from "../api";
import { useAuth } from "../context/AuthContext";

export function ApprovalQueue() {
  const { user } = useAuth();
  const [rows, setRows] = useState<Approval[]>();
  const [selected, select] = useState<Approval>();
  const [offset, page] = useState(0);
  const [revision, refresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    setRows(undefined);
    api.approvals(offset).then(items => { if (current) setRows(items); })
      .catch(e => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [offset, revision]);
  async function open(id: string) {
    setBusy(true); setError(""); setReason("");
    try { select(await api.approval(id)); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function decide(choice: "approve" | "reject") {
    if (!selected || busy) return;
    setBusy(true); setError("");
    try { select(await api.decide(selected.id, choice, reason.trim())); setReason(""); }
    catch (e) {
      setError((e as Error).message);
      try { select(await api.approval(selected.id)); } catch { select(undefined); }
    } finally { setBusy(false); refresh(v => v + 1); }
  }
  const own = selected?.maker === user?.id;
  const voted = selected?.decisions?.some(d => d.actor === user?.id);
  return <section className="panel"><h1>Review &amp; approvals</h1>
    {error && <p role="alert">{error}</p>}
    {!rows && !error && <p role="status">Loading approvals…</p>}
    {rows?.length === 0 && <p>No pending approvals on this page.</p>}
    <ul>{rows?.map(row => <li key={row.id}><button className="button secondary" disabled={busy}
      onClick={() => void open(row.id)}>{row.maker_name} · {row.currency} {row.amount}</button></li>)}</ul>
    {offset > 0 && <button disabled={busy} onClick={() => page(offset - 25)}>Previous page</button>}
    {rows?.length === 25 && <button disabled={busy} onClick={() => page(offset + 25)}>Next page</button>}
    {selected && <article><h2>Transfer review</h2><p>{selected.status}</p>
      <dl style={{overflowWrap:"anywhere"}}>{Object.entries({
        Reference:selected.id, Maker:selected.maker_name, From:selected.source_id, To:selected.destination_id,
        Amount:selected.currency+" "+selected.amount, Reservation:selected.hold_status,
        "Required reviewers":selected.required_count
      }).map(([label,value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <ul>{selected.decisions?.map(d => <li key={d.actor}>{d.actor} · {d.decision} · {d.reason}</li>)}</ul>
      {selected.status === "pending_approval" && (own ? <p>Another reviewer must decide your request.</p>
        : voted ? <p>Your decision has been recorded.</p> : user?.permissions.includes("approvals.decide") &&
        <fieldset disabled={busy}><legend>Independent decision</legend>
          <label>Decision reason <textarea maxLength={256} value={reason} onChange={e => setReason(e.target.value)}/></label>
          <button className="button primary" disabled={!reason.trim()} onClick={() => void decide("approve")}>Approve</button>
          <button className="button secondary" disabled={!reason.trim()} onClick={() => void decide("reject")}>Reject</button>
        </fieldset>)}</article>}
  </section>;
}
