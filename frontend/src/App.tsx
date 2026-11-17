import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArchitectureBento } from './components/ArchitectureBento';
import { Toaster, toast } from 'sonner';


const currency = new Intl.NumberFormat('en-US', {style:'currency', currency:'USD'});
const money = (cents: number) => currency.format(cents / 100);
const worstCase = import.meta.env.DEV && new URLSearchParams(location.search).get('data') === 'worst';
const accounts = worstCase
  ? ['International treasury operating account', 'Cross-border settlement reserve']
  : ['Operating cash', 'Settlement reserve'];
const accountIds = worstCase
  ? ['GB29NWBK60161331926819', 'DE89370400440532013000']
  : ['ACCT–001', 'ACCT–002'];
const opening = worstCase ? [987654321098765, 123456789012345] : [10000000, 2500000];
const newEntry = (amount: number, source: number, time = Date.now(), description = '') => ({
  amount, source, time, description, key: crypto.randomUUID(), id: crypto.randomUUID().slice(0, 8),
});
function seed() {
  const now = Date.now();
  return [newEntry(worstCase ? 1234567890123 : 25000, 0, now - 60000, worstCase
    ? 'Quarter-end reconciliation for international settlement batch SETTLEMENT20261117INTERNATIONAL0000007429'
    : ''), newEntry(75000, 1, now - 180000), newEntry(125000, 0, now - 300000)];
}
function HealthStatus() {
  const [status, setStatus] = useState('Checking API…');
  const [refresh, setRefresh] = useState(0);
  const previous = useRef('');

  useEffect(() => {
    const lifetime = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      let next = 'API unavailable';
      try {
        const signal = AbortSignal.any([lifetime.signal, AbortSignal.timeout(5000)]);
        const response = await fetch((import.meta.env.VITE_API_BASE_URL ?? '') + '/health/ready', { cache: 'no-store', signal });
        const body = await response.json();
        if (response.ok && body.status === 'ready') next = 'API ready';
        if (response.status === 503 && body.status === 'not_ready') next = 'API not ready';
      } catch {
        // A stopped backend or failed proxy leaves the simulator available.
      }
      if (lifetime.signal.aborted) return;
      if (previous.current && previous.current !== next) toast(next);
      previous.current = next;
      setStatus(next);
      timer = setTimeout(poll, 15000);
    }
    void poll();
    return () => { lifetime.abort(); clearTimeout(timer); };
  }, [refresh]);

  return <button className="quiet inline-flex items-center gap-2" title="Refresh API readiness"
    onClick={() => setRefresh(value => value + 1)}>
    <span aria-hidden="true" className={status === 'API ready' ? 'size-2 rounded-full bg-ledger-accent' : 'size-2 rounded-full bg-ledger-muted'} />
    <span role="status">{status}</span>
  </button>;
}

export function App() {
  const [entries, setEntries] = useState(seed);
  const seen = useRef(new Set(entries.map(entry => entry.key)));
  const dialog = useRef<HTMLDialogElement>(null);
  const [source, setSource] = useState(0);
  const balances = [...opening];
  for (const entry of entries) {
    balances[entry.source] -= entry.amount;
    balances[1 - entry.source] += entry.amount;
  }
  function post(entry: ReturnType<typeof newEntry>) {
    if (seen.current.has(entry.key)) {
      toast.info('Replay detected. Balances unchanged.');
      return;
    }
    seen.current.add(entry.key);
    setEntries(previous => [entry, ...previous]);
    toast.success('Simulated transfer posted', {description: money(entry.amount) + ' · Two journal entries recorded'});
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const field = event.currentTarget.elements.namedItem('amount') as HTMLInputElement;
    const cents = Math.round(Number(field.value) * 100);
    if (cents < 1 || cents > balances[source]) {
      field.setCustomValidity('Enter an amount within the available balance.');
      field.reportValidity();
      return;
    }
    post(newEntry(cents, source));
    dialog.current?.close();
  }
  async function copy(key: string) {
    try { await navigator.clipboard.writeText(key); toast.success('Idempotency key copied'); }
    catch { toast.error('Clipboard unavailable'); }
  }
  return <>
    <header><nav className="wrap nav" aria-label="Main navigation">
      <strong className="brand"><i aria-hidden="true">≋</i> LedgerOps</strong>
      <div className="nav-tools"><HealthStatus /><button className="primary" onClick={() => dialog.current?.showModal()}>Launch Sandbox</button></div>
    </nav></header>
    <main className="wrap">
      <aside>◇ &nbsp; Simulated cloud-native banking &amp; double-entry ledger environment</aside>
      <section className="hero">
        <div><h1>Every transfer,<br/><span>in balance.</span></h1>
          <p>Explore a double-entry banking core built for reliability engineering. Post a simulated transfer, inspect both journal entries, and check service readiness live.</p>
          <div className="actions"><a className="architecture-link" href="#architecture">Explore the architecture ↓</a><a href="#journal">View journal</a></div>
        </div>
        <article className="preview" aria-label="Interactive ledger preview"><div className="caption">Ledger sandbox <small>USD</small></div>
          {accounts.map((name, i) => <div className="account" key={name}><div>{name}<code>{accountIds[i]}</code></div><b>{money(balances[i])}</b></div>)}
          <div className="total"><span>Combined balance</span><b>{money(balances[0] + balances[1])}</b></div>
          <div className="posting"><small>Latest journal entry · #{entries[0].id}</small>
            <div><span>Debit · {accounts[1 - entries[0].source]}</span><b>{money(entries[0].amount)}</b></div>
            <div><span>Credit · {accounts[entries[0].source]}</span><b>{money(entries[0].amount)}</b></div>
          </div>
          <button className="primary transfer" onClick={() => dialog.current?.showModal()}>Simulate Transfer ↗</button>
        </article>
      </section>
    </main>
    <ArchitectureBento />
    <div className="wrap">
      <section id="journal"><div className="caption"><h2>Transaction journal</h2><small>{entries.length} transfers</small></div>
        <p>Each transfer debits the destination asset account and credits the source.</p>
        <div className="scroll" tabIndex={0} role="region" aria-label="Transaction journal"><table><thead><tr>{['Time','Ledger reference','Debit','Credit','Amount','Idempotency'].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>
          {entries.map(e => <tr key={e.key}><td>{new Date(e.time).toLocaleTimeString('en-GB')}</td><td>#{e.id}{e.description && <span className="journal-description">{e.description}</span>}</td><td>{accounts[1-e.source]}</td><td>{accounts[e.source]}</td><td>{money(e.amount)}</td><td><span className="badge">✓ Recorded</span> <button className="link" onClick={() => copy(e.key)}>Copy key</button> <button className="link" onClick={() => post(e)}>Replay</button></td></tr>)}
        </tbody></table></div>
      </section>
    </div>
    <dialog ref={dialog} aria-labelledby="transfer-title"><form onSubmit={submit}><h2 id="transfer-title">Simulate transfer</h2>
      <label>From account<select value={source} onChange={e => {setSource(Number(e.target.value)); (e.currentTarget.form?.elements.namedItem('amount') as HTMLInputElement)?.setCustomValidity('');}}>{accounts.map((a,i) => <option key={a} value={i}>{a}</option>)}</select></label>
      <p>To {accounts[1-source]} · Available {money(balances[source])}</p>
      <label>Amount in USD<input name="amount" type="number" step=".01" min=".01" max={balances[source]/100} defaultValue="250.00" required onInput={e => e.currentTarget.setCustomValidity('')}/></label>
      <div className="actions"><button className="primary">Post transfer</button><button type="button" className="quiet" onClick={() => dialog.current?.close()}>Cancel</button></div>
    </form></dialog>
    <Toaster theme="dark" position="bottom-right" closeButton/>
  </>;
}
