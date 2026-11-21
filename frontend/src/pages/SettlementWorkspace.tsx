import { useEffect, useState } from "react";
import { api, type SettlementKind, type SettlementRecord } from "../api";
import { useAuth } from "../context/AuthContext";

const sections: Record<SettlementKind,string> = {
  batches:"Settlement batches", statements:"Statements", "reconciliation-runs":"Reconciliation runs"
};
function fields(row: Record<string,unknown>) {
  return <dl className="detail-grid">{Object.entries(row).filter(([,v])=>v!==null && typeof v!=="object")
    .map(([k,v])=><div key={k}><dt>{k.replaceAll("_"," ")}</dt><dd className="mono">{String(v)}</dd></div>)}</dl>;
}

export function SettlementWorkspace({initial}:{initial:SettlementKind}) {
  const {user}=useAuth();
  const write=user?.permissions.includes("payments.submit");
  const [kind,choose]=useState(initial), [rows,setRows]=useState<SettlementRecord[]>([]);
  const [selected,select]=useState<SettlementRecord>(), [items,setItems]=useState<Record<string,unknown>[]>([]);
  const [customers,setCustomers]=useState<Map<string,string>>(new Map()), [customer,setCustomer]=useState("");
  const [file,setFile]=useState<File>(), [offset,page]=useState(0), [itemOffset,itemPage]=useState(0);
  const [revision,refresh]=useState(0), [busy,setBusy]=useState(false), [error,setError]=useState("");
  useEffect(()=>{
    let live=true;
    if(write) api.accounts().then(accounts=>{
      if(!live)return;
      const choices=new Map<string,string>();
      accounts.forEach(a=>{if(a.customer_id && a.membership_role!=="viewer")choices.set(a.customer_id,a.customer_name);});
      setCustomers(choices);setCustomer(choices.keys().next().value || "");
    }).catch(e=>{if(live)setError(e.message);});
    return ()=>{live=false;};
  },[write]);
  useEffect(()=>{
    let live=true; setRows([]);
    api.settlementList(kind,offset).then(r=>{if(live)setRows(r);}).catch(e=>{if(live)setError(e.message);});
    return ()=>{live=false;};
  },[kind,offset,revision]);
  useEffect(()=>{
    let live=true;setItems([]);
    if(selected) api.settlementItems(kind,selected.id,itemOffset).then(r=>{if(live)setItems(r);}).catch(e=>{if(live)setError(e.message);});
    return ()=>{live=false;};
  },[kind,selected,itemOffset]);
  useEffect(()=>{
    const id=new URLSearchParams(location.search).get("batch");
    let live=true;
    if(id) api.settlementBatch(id).then(r=>{if(live)select(r);}).catch(e=>{if(live)setError(e.message);});
    return ()=>{live=false;};
  },[]);
  async function mutate(target:SettlementKind, action:()=>Promise<SettlementRecord>) {
    setBusy(true);setError("");
    try {const result=await action();choose(target);page(0);itemPage(0);select(result);refresh(v=>v+1);}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  return <main className="workspace-stack"><header className="page-header"><h1>Settlement Management</h1></header>
    {error && <p role="alert">{error}</p>}
    <nav className="button-row" aria-label="Settlement views">{(Object.keys(sections) as SettlementKind[]).map(k=>
      <button className="button secondary" key={k} disabled={busy} aria-pressed={kind===k}
        onClick={()=>{choose(k);page(0);select(undefined);itemPage(0);setError("");}}>{sections[k]}</button>)}</nav>
    {write && kind!=="reconciliation-runs" && <section className="panel"><label>Workspace<select value={customer} onChange={e=>setCustomer(e.target.value)}>
      {[...customers].map(([id,name])=><option key={id} value={id}>{name} · {id.slice(0,8)}</option>)}</select></label>
      {kind==="batches"?<button className="button primary" disabled={busy||!customer} onClick={()=>void mutate(kind,()=>api.makeBatch(customer))}>Create batch</button>:
      <><label>Simulated rail CSV<input type="file" accept=".csv,text/csv" onChange={e=>setFile(e.target.files?.[0])}/></label>
      <button className="button primary" disabled={busy||!customer||!file} onClick={()=>file && void mutate(kind,()=>api.importStatement(customer,file))}>Import statement</button></>}</section>}
    <section className="panel"><h2>{sections[kind]}</h2>{rows.length===0 && <p>No records on this page.</p>}
      {rows.map(r=><button key={r.id} className="activity-row" onClick={()=>{select(r);itemPage(0);}}>
        <span className="mono">{r.filename||r.id}</span><span>{r.status}</span><span>{r.total && "INR "+r.total}</span>
        {kind==="batches" && <span>{r.item_count} items · {r.settled_count} settled · {r.failed_count} failed · {new Date(r.created_at).toLocaleString()}</span>}</button>)}
      <button disabled={!offset} onClick={()=>page(offset-25)}>Previous page</button>
      <button disabled={rows.length<25} onClick={()=>page(offset+25)}>Next page</button></section>
    {selected && <section className="panel"><h2>Record detail</h2>{fields({...selected})}
      {selected.replayed && <p role="status">This statement was already imported.</p>}
      {write && kind==="batches" && selected.status!=="settled" && <button className="button primary" disabled={busy} onClick={()=>void mutate(kind,()=>api.processBatch(selected.id))}>Process batch</button>}
      {write && kind==="statements" && <button className="button primary" disabled={busy} onClick={()=>void mutate("reconciliation-runs",()=>api.reconcile(selected.id))}>Run reconciliation</button>}
      <h3>Items</h3>{items.map((r,i)=><article key={String(r.id||r.payment_id||i)}>{fields(r)}
      {typeof r.payment_id==="string" && <a href={"/console/payments?payment="+encodeURIComponent(r.payment_id)}>View payment</a>}
      {((r.evidence as {internal?:{batch_id?:string}} | null)?.internal?.batch_id) && <a href={"/console/settlements?batch="+encodeURIComponent((r.evidence as {internal:{batch_id:string}}).internal.batch_id)}>View settlement batch</a>}
      {r.evidence!=null && <details><summary>Matching evidence</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{JSON.stringify(r.evidence,null,2)}</pre></details>}</article>)}
      <button disabled={!itemOffset} onClick={()=>itemPage(itemOffset-25)}>Previous items</button>
      <button disabled={items.length<25} onClick={()=>itemPage(itemOffset+25)}>Next items</button></section>}
  </main>;
}
