import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { api, type Account, type Payment, type PaymentCommand } from "../api";
import { useAuth } from "../context/AuthContext";

const empty: PaymentCommand = {
  source_id: "", beneficiary_name: "", destination_reference: "",
  customer_reference: "", amount: "", currency: "INR",
};

export function PaymentHub() {
  const { user } = useAuth();
  const [payments, setPayments] = useState<Payment[]>();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selected, select] = useState<Payment>();
  const [command, setCommand] = useState(empty);
  const [offset, setOffset] = useState(0);
  const [revision, refresh] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = useRef(crypto.randomUUID());
  const canCreate = user?.permissions.includes("payments.create");
  const activeAccounts = useMemo(() => accounts.filter(a => a.status === "active"), [accounts]);

  useEffect(() => {
    let current = true;
    setPayments(undefined);
    Promise.all([api.payments(offset), canCreate ? api.accounts() : Promise.resolve([])])
      .then(([rows, available]) => {
        if (!current) return;
        setPayments(rows); setAccounts(available);
        setCommand(value => ({ ...value, source_id: value.source_id || available[0]?.id || "" }));
      })
      .catch(e => { if (current) setError((e as Error).message); });
    return () => { current = false; };
  }, [offset, revision, canCreate]);

  async function open(id: string) {
    setBusy(true); setError("");
    try { select(await api.payment(id)); } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function create() {
    setBusy(true); setError("");
    try {
      const payment = await api.createPayment(command, key.current);
      select(payment); setCommand({...empty, source_id: command.source_id});
      key.current = crypto.randomUUID(); refresh(value => value + 1);
      toast.success("Payment instruction reserved");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function act(action: "submit" | "cancel") {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      const payment = action === "submit"
        ? await api.submitPayment(selected.id) : await api.cancelPayment(selected.id);
      select(payment); refresh(value => value + 1);
      toast.success(action === "submit" ? "Simulated rail response recorded" : "Payment cancelled");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="workspace-stack">
    <header className="page-header"><div><p className="eyebrow">Simulated financial operations</p>
      <h1>Payment Hub</h1><p>Create reserved INR instructions and track simulated rail outcomes.</p>
    </div><span className="status-badge warning">SIMULATED RAIL</span></header>
    {error && <p role="alert" className="error-message">{error}</p>}
    {canCreate && <section className="panel"><h2>New payment instruction</h2>
      <div className="form-grid">
        <label>Source account<select value={command.source_id}
          onChange={e => setCommand({...command,source_id:e.target.value})}>
          {activeAccounts.map(a => <option key={a.id} value={a.id}>{a.reference} · INR {a.available_balance}</option>)}
        </select></label>
        <label>Beneficiary name<input value={command.beneficiary_name}
          onChange={e => setCommand({...command,beneficiary_name:e.target.value})}/></label>
        <label>Destination reference<input value={command.destination_reference}
          onChange={e => setCommand({...command,destination_reference:e.target.value})}/></label>
        <label>Customer reference<input value={command.customer_reference}
          onChange={e => setCommand({...command,customer_reference:e.target.value})}/></label>
        <label>Amount in INR<input inputMode="decimal" value={command.amount}
          onChange={e => setCommand({...command,amount:e.target.value})}/></label>
      </div><button className="button primary" disabled={busy || !command.source_id ||
        !command.beneficiary_name.trim() || !command.destination_reference.trim() ||
        !command.customer_reference.trim() || !/^(0|[1-9]\d{0,15})(\.\d{1,2})?$/.test(command.amount)}
        onClick={() => void create()}>Create and reserve</button></section>}
    <section className="panel"><h2>Payment instructions</h2>
      {!payments && !error && <p role="status">Loading payment instructions…</p>}
      {payments?.length === 0 && <p>No payment instructions on this page.</p>}
      <ul className="activity-list">{payments?.map(payment => <li key={payment.id}>
        <button className="activity-row" disabled={busy} onClick={() => void open(payment.id)}>
          <span><strong>{payment.beneficiary_name}</strong><small>{payment.customer_reference}</small></span>
          <span className="mono">INR {payment.amount}</span><span>{payment.status}</span>
        </button></li>)}</ul>
      {offset > 0 && <button onClick={() => setOffset(offset - 25)}>Previous</button>}
      {payments?.length === 25 && <button onClick={() => setOffset(offset + 25)}>Next</button>}
    </section>
    {selected && <section className="panel"><h2>Instruction detail</h2>
      <dl className="detail-grid">{Object.entries({
        Status:selected.status, Source:selected.source_id, Beneficiary:selected.beneficiary_name,
        Destination:selected.destination_reference, Amount:`${selected.currency} ${selected.amount}`,
        Rail:"SIMULATED INR", "Provider reference":selected.provider_reference,
        Approval:selected.approval_status || "Not required", Created:new Date(selected.created_at).toLocaleString(),
        Updated:new Date(selected.updated_at).toLocaleString()
      }).map(([label,value]) => <div key={label}><dt>{label}</dt><dd className="mono">{value}</dd></div>)}</dl>
      {selected.status === "accepted" && <p className="small-note">Accepted by the simulated rail. Settlement is still pending.</p>}
      <div className="button-row">
        {["ready_for_submission","outcome_unknown"].includes(selected.status) &&
          user?.permissions.includes("payments.submit") &&
          <button className="button primary" disabled={busy} onClick={() => void act("submit")}>Submit to simulated rail</button>}
        {["pending_approval","ready_for_submission"].includes(selected.status) &&
          user?.permissions.includes("payments.cancel") &&
          <button className="button secondary" disabled={busy} onClick={() => void act("cancel")}>Cancel instruction</button>}
      </div><h3>Lifecycle</h3><ol>{selected.events?.map(event =>
        <li key={event.id}><strong>{event.kind}</strong> · {event.detail}</li>)}</ol>
    </section>}
  </div>;
}
