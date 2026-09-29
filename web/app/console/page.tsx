"use client";
import { useEffect, useState } from "react";
import { Glass } from "@/components/Glass";
import { FlowGraph } from "@/components/FlowGraph";
import { API, Final, useClaimStream } from "@/lib/useClaimStream";
import { DemoBar, useDemo } from "@/components/DemoBar";

type Item = { id: string; who: string; amt: number; conf: number; claim: Record<string, unknown> };
const QUEUE: Item[] = [
  { id: "C-101", who: "Asha R.", amt: 1499, conf: 0.95, claim: { id: "C-101", order_id: "ORD101", text: "box was crushed and the item is broken", damage_conf: 0.95, amount_inr: 1499, days_since_delivery: 2 } },
  { id: "C-102", who: "Vikram S.", amt: 999, conf: 0.93, claim: { id: "C-102", order_id: "ORD102", text: "product came with a dent and scratches", damage_conf: 0.93, amount_inr: 999, days_since_delivery: 1 } },
  { id: "C-103", who: "Neha T.", amt: 2999, conf: 0.61, claim: { id: "C-103", order_id: "ORD103", text: "received it damaged, photo attached", damage_conf: 0.61, amount_inr: 2999, days_since_delivery: 3 } },
  { id: "C-104", who: "Rohit K.", amt: 1499, conf: 0.9, claim: { id: "C-104", order_id: "ORD104", text: "screen is cracked when it arrived", damage_conf: 0.9, amount_inr: 1499, days_since_delivery: 12 } },
];

const post = (path: string, body: unknown) =>
  API ? fetch(`${API}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => null) : Promise.resolve(null);

function downloadCsv(id: string, f: Final) {
  const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const rows = [["id", "decision", "rule", "lane", "ms", "verified", "trace"],
    [id, f.final.decision, f.final.rule, f.final.lane, f.ms, f.verified, JSON.stringify(f.trace ?? [])]];
  const blob = new Blob([rows.map((r) => r.map(esc).join(",")).join("\n")], { type: "text/csv" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${id}-audit.csv`; a.click();
}

export default function Console() {
  const [sel, setSel] = useState(QUEUE[0]);
  const { status, final, busy, run, log } = useClaimStream();
  const demo = useDemo();
  const [inject, setInject] = useState(false);
  const [results, setResults] = useState<Record<string, Final>>({});
  const [reviewed, setReviewed] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [sent, setSent] = useState<Record<string, boolean>>({});
  const [analysing, setAnalysing] = useState(false);

  const res = results[sel.id];
  const ready = QUEUE.filter((q) => results[q.id]?.final.lane === "ready" && !reviewed[q.id]);

  const analyse = async (q: Item) => {
    const r = await run({ ...q.claim, inject_failure: inject });
    if (r) { setResults((m) => ({ ...m, [q.id]: r })); setDrafts((d) => ({ ...d, [q.id]: r.draft_reply ?? "" })); }
  };
  const analyseAll = async () => {
    setAnalysing(true);
    for (const q of QUEUE) { setSel(q); await analyse(q); }
    setAnalysing(false);
  };
  const approve = async () => {
    if (!res) return;
    await post("/decisions", { id: sel.id, action: "approve" });
    setReviewed((r) => ({ ...r, [sel.id]: "approved" }));
  };
  const reject = async () => {
    if (!res) return;
    if (!rejecting) { setRejecting(true); return; }
    if (!reason.trim()) return;                                // a reason is required: it feeds the eval set
    await post("/decisions", { id: sel.id, action: "reject", reason });
    setReviewed((r) => ({ ...r, [sel.id]: `rejected: ${reason}` })); setRejecting(false); setReason("");
  };
  const approveAllReady = async () => {
    await post("/decisions/batch", { ids: ready.map((q) => q.id) });
    setReviewed((r) => ({ ...r, ...Object.fromEntries(ready.map((q) => [q.id, "approved (batch)"])) }));
  };
  const sendReply = async () => {
    await post("/replies", { id: sel.id, text: drafts[sel.id] });
    setSent((s) => ({ ...s, [sel.id]: true }));
  };

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (["INPUT", "TEXTAREA"].includes((e.target as HTMLElement).tagName)) return;
      if (e.key.toLowerCase() === "a") approve();
      if (e.key.toLowerCase() === "r") reject();
    };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  });

  const laneOf = (q: Item) => (results[q.id] ? results[q.id].final.lane : "new");

  return (
    <div className="wrap" style={{ maxWidth: 1100 }}>
      <h1>Agent console</h1>
      <p className="muted">Ready lane: approve in one tap. Review lane: needs a human look. Press A to approve, R to reject.</p>
      {demo && <DemoBar inject={inject} setInject={setInject} log={log} trace={final?.trace} />}
      <div className="grid" style={{ gridTemplateColumns: "minmax(200px,1fr) minmax(0,1.5fr) minmax(200px,1fr)" }}>
        <Glass>
          <h2>Queue</h2>
          <button className="btn go" style={{ width: "100%", marginBottom: 10 }} disabled={busy || analysing} onClick={analyseAll}>
            {analysing ? "Analysing..." : "Analyse all"}
          </button>
          {QUEUE.map((q) => (
            <div key={q.id} onClick={() => setSel(q)} style={{ padding: 10, borderRadius: 14, cursor: "pointer", marginBottom: 6,
              background: sel.id === q.id ? "rgba(255,255,255,.16)" : "transparent" }}>
              <b>{q.id}</b> <span className="pill">{reviewed[q.id] ? "done" : laneOf(q)}</span>
              <div className="muted">{q.who} · ₹{q.amt}</div>
            </div>
          ))}
          {ready.length > 0 && (
            <button className="btn go" style={{ width: "100%", marginTop: 8 }} onClick={approveAllReady}>Approve all ready ({ready.length})</button>
          )}
        </Glass>
        <Glass>
          <h2>Evidence · {sel.id}</h2>
          <p>Damage confidence: <b>{Math.round(sel.conf * 100)}%</b> · Amount: <b>₹{sel.amt}</b></p>
          <p className="muted">"{String(sel.claim.text)}"</p>
          <button className="btn go" disabled={busy || analysing} onClick={() => analyse(sel)}>{busy ? "Running..." : "Run agent"}</button>
          {res && (
            <Glass solid style={{ marginTop: 14 }}>
              <div className="muted">Why</div>
              <div><b style={{ textTransform: "capitalize" }}>{res.final.decision}</b> · rule {res.final.rule} · {res.final.lane} lane</div>
              <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                <button className="btn go" onClick={approve}>Approve (A)</button>
                <button className="btn no" onClick={reject}>{rejecting ? "Confirm reject" : "Reject (R)"}</button>
                <button className="btn" style={{ background: "rgba(255,255,255,.14)" }}
                  onClick={() => API ? window.open(`${API}/audit/${sel.id}.csv`) : downloadCsv(sel.id, res)}>Export CSV</button>
              </div>
              {rejecting && <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason required (saved to the override set)"
                style={{ marginTop: 10, width: "100%", padding: 10, borderRadius: 12, border: "1px solid rgba(255,255,255,.2)", background: "rgba(0,0,0,.25)", color: "inherit" }} />}
              {reviewed[sel.id] && <p className="muted" style={{ color: "#2ee6a6" }}>Recorded: {reviewed[sel.id]}</p>}
              <div className="muted" style={{ marginTop: 14 }}>Reply to customer (editable)</div>
              <textarea value={drafts[sel.id] ?? ""} onChange={(e) => setDrafts((d) => ({ ...d, [sel.id]: e.target.value }))} />
              <button className="btn go" style={{ marginTop: 8 }} disabled={sent[sel.id]} onClick={sendReply}>{sent[sel.id] ? "Logged" : "Send reply"}</button>
              {sent[sel.id] && <span className="muted"> Logged only. Email/WhatsApp delivery is not connected yet.</span>}
            </Glass>
          )}
        </Glass>
        <Glass>
          <h2>Live flow</h2>
          <FlowGraph status={status} />
        </Glass>
      </div>
    </div>
  );
}
