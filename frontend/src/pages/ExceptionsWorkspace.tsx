import { useEffect, useState } from "react";
import { api, type ExceptionAssignee, type ExceptionEvent, type ExceptionPage, type ExceptionRecord } from "../api";
import { useAuth } from "../context/AuthContext";

const PAGE_SIZE = 25;
// Mirror backend/app/modules/finance/exceptions.py: transition reasons are short, notes and
// resolution summaries are the longer free-text record.
const REASON_MAX = 500;
const NOTE_MAX = 2000;

const STATUS_LABELS: Record<string, string> = {
  open: "Open", investigating: "Investigating", awaiting_information: "Awaiting information",
  resolved: "Resolved", closed: "Closed",
};
const SEVERITIES = ["low", "medium", "high", "critical"];
const SOURCES = ["payment", "approval", "settlement", "reconciliation"];
const TYPE_LABELS: Record<string, string> = {
  payment_failed: "Payment rejected",
  payment_outcome_unknown: "Payment outcome unknown",
  approval_expired: "Approval expired",
  settlement_failed: "Settlement failed",
  amount_mismatch: "Reconciliation amount mismatch",
  currency_mismatch: "Reconciliation currency mismatch",
  direction_mismatch: "Reconciliation direction mismatch",
  status_mismatch: "Reconciliation status mismatch",
  missing_internal_record: "Missing internal settlement",
  missing_statement_record: "Missing statement record",
  duplicate_external_reference: "Duplicate provider reference",
  timing_difference: "Settlement timing difference",
};

function eventSummary(event: ExceptionEvent): string {
  const name = event.metadata?.assigned_name;
  if (event.kind === "assigned") return name ? `Assigned to ${name}` : "Assigned";
  if (event.kind === "reassigned") return name ? `Reassigned to ${name}` : "Reassigned";
  if (event.kind === "created") return "Exception recorded";
  return event.note || (event.next_status ? STATUS_LABELS[event.next_status] ?? event.next_status : "Recorded");
}

type Assignees = { state: "idle" | "loading" | "ready" | "error"; people: ExceptionAssignee[]; message: string };
const NO_ASSIGNEES: Assignees = { state: "idle", people: [], message: "" };

export function ExceptionsWorkspace() {
  const { user } = useAuth();
  const manage = Boolean(user?.permissions.includes("exceptions.manage"));
  const [page, setPage] = useState<ExceptionPage>();
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ExceptionRecord>();
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [type, setType] = useState("");
  const [source, setSource] = useState("");
  const [createdOn, setCreatedOn] = useState("");
  const [offset, setOffset] = useState(0);
  const [note, setNote] = useState("");
  const [listError, setListError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, refresh] = useState(0);
  const [assignees, setAssignees] = useState<Assignees>(NO_ASSIGNEES);
  const [assignee, setAssignee] = useState("");
  const [assigneeRevision, retryAssignees] = useState(0);

  useEffect(() => {
    let current = true;
    setLoading(true);
    const query = new URLSearchParams();
    if (status) query.set("status", status);
    if (severity) query.set("severity", severity);
    if (type) query.set("exception_type", type);
    if (source) query.set("source_domain", source);
    if (createdOn) query.set("created_on", createdOn);
    query.set("limit", String(PAGE_SIZE));
    api.exceptions(offset, "&" + query.toString())
      .then(value => {
        if (!current) return;
        if (value.items.length === 0 && offset > 0 && value.total > 0) {
          setOffset(Math.floor((value.total - 1) / PAGE_SIZE) * PAGE_SIZE); // the page emptied: step back
          return;
        }
        setPage(value); setListError(""); setLoading(false);
      })
      .catch(value => { if (current) { setListError((value as Error).message); setLoading(false); } });
    return () => { current = false; };
  }, [status, severity, type, source, createdOn, offset, revision]);

  const selectedId = selected?.id;
  const assignable = manage && selected !== undefined && selected.status !== "closed";
  useEffect(() => {
    if (!selectedId || !assignable) { setAssignees(NO_ASSIGNEES); return; }
    let current = true;
    setAssignees({ state: "loading", people: [], message: "" });
    setAssignee("");
    api.exceptionAssignees(selectedId)
      .then(people => { if (current) setAssignees({ state: "ready", people, message: "" }); })
      .catch(value => { if (current) setAssignees({ state: "error", people: [], message: (value as Error).message }); });
    return () => { current = false; };
  }, [selectedId, assignable, assigneeRevision]);

  async function open(id: string) {
    setBusy(true); setActionError(""); setNotice(""); setNote("");
    try { setSelected(await api.exception(id)); } catch (value) { setListError((value as Error).message); }
    finally { setBusy(false); }
  }
  async function action(run: () => Promise<ExceptionRecord>, message = "") {
    setBusy(true); setActionError(""); setNotice("");
    try { setSelected(await run()); setNote(""); setNotice(message); refresh(value => value + 1); }
    catch (value) { setActionError((value as Error).message); }
    finally { setBusy(false); }
  }
  function submitAssignment(record: ExceptionRecord) {
    const person = assignees.people.find(item => item.id === assignee);
    if (!person) return;
    void action(async () => {
      const updated = await api.assignException(record.id, person.id);
      setAssignee("");
      return updated;
    }, `${record.assigned_user_id ? "Reassigned" : "Assigned"} to ${person.display_name}.`);
  }

  const reason = note.trim();
  const reasonTooLong = reason.length > REASON_MAX;
  const pages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1;
  const resetPage = (change: () => void) => { change(); setOffset(0); };

  return <main className="workspace-stack">
    <header className="page-header"><div><p className="eyebrow">Customer-scoped operations</p><h1>Exceptions & Investigations</h1><p>Investigate observed workflow discrepancies without changing financial history.</p></div></header>
    {listError && <p role="alert" className="error-message">{listError}</p>}
    <section className="panel" aria-label="Queue filters"><div className="form-grid">
      <label>Status<select value={status} onChange={e => resetPage(() => setStatus(e.target.value))}><option value="">All statuses</option>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>Severity<select value={severity} onChange={e => resetPage(() => setSeverity(e.target.value))}><option value="">All severities</option>{SEVERITIES.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
      <label>Type<select value={type} onChange={e => resetPage(() => setType(e.target.value))}><option value="">All types</option>{Object.entries(TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>Source<select value={source} onChange={e => resetPage(() => setSource(e.target.value))}><option value="">All sources</option>{SOURCES.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
      <label>Created on<input type="date" value={createdOn} onChange={e => resetPage(() => setCreatedOn(e.target.value))}/></label>
    </div></section>
    <section className="panel">
      <h2>Exception queue</h2>
      {!page && loading && <p role="status">Loading exceptions…</p>}
      {page?.items.length === 0 && <p>No exceptions match these filters.</p>}
      <ul className="activity-list">{page?.items.map(row => <li key={row.id}><button className="activity-row" disabled={busy} onClick={() => void open(row.id)}><span><strong>{row.title}</strong><small className="mono">{row.reference}</small></span><span>{row.severity}</span><span>{STATUS_LABELS[row.status] ?? row.status}</span><small>{row.assigned_name || "Unassigned"}</small></button></li>)}</ul>
      {page && <div className="button-row">
        <button className="button secondary" disabled={busy || loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
        <small>Page {Math.floor(offset / PAGE_SIZE) + 1} of {pages} · {page.total} results</small>
        <button className="button secondary" disabled={busy || loading || offset + PAGE_SIZE >= page.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
      </div>}
    </section>
    {selected && <section className="panel" aria-label="Exception detail">
      <h2>{selected.title}</h2><p>{selected.description}</p>
      {actionError && <p role="alert" className="error-message">{actionError}</p>}
      {notice && <p role="status">{notice}</p>}
      <dl className="detail-grid">
        <div><dt>Reference</dt><dd className="mono">{selected.reference}</dd></div>
        <div><dt>Source</dt><dd className="mono">{selected.source_domain} · {selected.source_reference}</dd></div>
        <div><dt>Severity</dt><dd>{selected.severity}</dd></div>
        <div><dt>Status</dt><dd>{STATUS_LABELS[selected.status] ?? selected.status}</dd></div>
        <div><dt>Assignee</dt><dd>{selected.assigned_name || "Unassigned"}</dd></div>
        {selected.resolution_summary && <div><dt>Resolution</dt><dd>{selected.resolution_summary}</dd></div>}
      </dl>
      {assignable && <section aria-labelledby="assignment-heading">
        <h3 id="assignment-heading">Assignment</h3>
        {assignees.state === "loading" && <p role="status">Loading eligible assignees…</p>}
        {assignees.state === "error" && <p role="alert" className="error-message">{assignees.message} <button className="button secondary" onClick={() => retryAssignees(value => value + 1)}>Retry</button></p>}
        {assignees.state === "ready" && assignees.people.length === 0 && <p>No eligible assignees.</p>}
        {assignees.state === "ready" && assignees.people.length > 0 && <div className="form-grid">
          <label>Assignee<select value={assignee} disabled={busy} onChange={e => setAssignee(e.target.value)}><option value="">Select a person</option>{assignees.people.map(person => <option key={person.id} value={person.id}>{person.display_name}{person.id === selected.assigned_user_id ? " (current)" : ""}</option>)}</select></label>
          <button className="button secondary" disabled={busy || !assignee || assignee === selected.assigned_user_id} onClick={() => submitAssignment(selected)}>{selected.assigned_user_id ? "Reassign" : "Assign"}</button>
        </div>}
      </section>}
      {assignable && <>
        <div className="button-row">
          {selected.status === "open" && <button className="button primary" disabled={busy} onClick={() => void action(() => api.transitionException(selected.id, "investigating"))}>Start investigation</button>}
          {["open", "investigating"].includes(selected.status) && <button className="button secondary" disabled={busy || !reason || reasonTooLong} onClick={() => void action(() => api.transitionException(selected.id, "awaiting_information", reason))}>Await information</button>}
          {selected.status === "awaiting_information" && <button className="button primary" disabled={busy} onClick={() => void action(() => api.transitionException(selected.id, "investigating"))}>Resume investigation</button>}
        </div>
        <label>Operational note or resolution summary<textarea value={note} onChange={e => setNote(e.target.value)} maxLength={NOTE_MAX} aria-describedby="note-limits"/></label>
        <small id="note-limits">{note.length}/{NOTE_MAX} characters. A reason to await information or to close is limited to {REASON_MAX}.{reasonTooLong && <strong role="alert"> Shorten the text to use it as a reason.</strong>}</small>
        <div className="button-row">
          {selected.status === "investigating" && <button className="button primary" disabled={busy || !reason} onClick={() => void action(() => api.resolveException(selected.id, reason))}>Resolve exception</button>}
          {selected.status === "resolved" && <button className="button primary" disabled={busy || !reason || reasonTooLong} onClick={() => void action(() => api.closeException(selected.id, reason))}>Close exception</button>}
          <button className="button secondary" disabled={busy || !reason} onClick={() => void action(() => api.noteException(selected.id, reason))}>Add note</button>
        </div>
      </>}
      <h3>Investigation history</h3>
      <ol>{selected.events?.map(event => <li key={event.id}><strong>{eventSummary(event)}</strong><small> {event.actor_name || "System"} · {new Date(event.occurred_at).toLocaleString()}</small></li>)}</ol>
    </section>}
  </main>;
}
