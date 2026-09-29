"use client";
import { useEffect, useState } from "react";
import { Glass } from "@/components/Glass";
import { FlowGraph } from "@/components/FlowGraph";
import { useClaimStream } from "@/lib/useClaimStream";
import { DemoBar, useDemo } from "@/components/DemoBar";

const QUEUE = [
  { id: "C-101", who: "Asha R.", amt: 1499, conf: 0.95, lane: "ready", claim: { id: "C-101", order_id: "ORD101", damage_conf: 0.95, amount_inr: 1499, days_since_delivery: 2 } },
  { id: "C-102", who: "Vikram S.", amt: 999, conf: 0.93, lane: "ready", claim: { id: "C-102", order_id: "ORD102", damage_conf: 0.93, amount_inr: 999, days_since_delivery: 1 } },
  { id: "C-103", who: "Neha T.", amt: 2999, conf: 0.61, lane: "review", claim: { id: "C-103", order_id: "ORD103", damage_conf: 0.61, amount_inr: 2999, days_since_delivery: 3 } },
];

export default function Console() {
  const [sel, setSel] = useState(QUEUE[0]);
  const { status, final, busy, run, log } = useClaimStream();
  const demo = useDemo();
  const [inject, setInject] = useState(false);
  const [reviewed, setReviewed] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);

  const approve = () => final && setReviewed((r) => ({ ...r, [sel.id]: "approved" }));
  const reject = () => {
    if (!final) return;
    if (!rejecting) { setRejecting(true); return; }
    setReviewed((r) => ({ ...r, [sel.id]: `rejected: ${reason || "no reason"}` })); setRejecting(false); setReason("");
  };
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT") return;
      if (e.key.toLowerCase() === "a") approve();
      if (e.key.toLowerCase() === "r") reject();
    };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  });

  return (
    <div className="wrap" style={{ maxWidth: 1100 }}>
      <h1>Agent console</h1>
      <p className="muted">Ready lane: high-confidence cases you can approve in one tap. Review lane: needs a human look.</p>
      {demo && <DemoBar inject={inject} setInject={setInject} log={log} trace={final?.trace} />}
      <div className="grid" style={{ gridTemplateColumns: "minmax(200px,1fr) minmax(0,1.4fr) minmax(200px,1fr)" }}>
        <Glass>
          <h2>Queue</h2>
          {QUEUE.map((q) => (
            <div key={q.id} onClick={() => setSel(q)} style={{ padding: 10, borderRadius: 14, cursor: "pointer", marginBottom: 6,
              background: sel.id === q.id ? "rgba(255,255,255,.16)" : "transparent" }}>
              <b>{q.id}</b> <span className="pill">{q.lane}</span>
              <div className="muted">{q.who} · ₹{q.amt}</div>
            </div>
          ))}
        </Glass>
        <Glass>
          <h2>Evidence · {sel.id}</h2>
          <div className="muted">Photo heatmap, invoice spans and order record appear here once the ML stack lands.</div>
          <p>Damage confidence: <b>{Math.round(sel.conf * 100)}%</b></p>
          <p>Amount: <b>₹{sel.amt}</b></p>
          <button className="btn go" disabled={busy} onClick={() => run({ ...sel.claim, inject_failure: inject })}>{busy ? "Running..." : "Run agent"}</button>
          {final && (
            <Glass solid style={{ marginTop: 14 }}>
              <div className="muted">Why</div>
              <div><b style={{ textTransform: "capitalize" }}>{final.final.decision}</b> · rule {final.final.rule}</div>
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <button className="btn go" onClick={approve}>Approve (A)</button>
                <button className="btn no" onClick={reject}>{rejecting ? "Confirm reject" : "Reject (R)"}</button>
              </div>
              {rejecting && <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (saved to the eval set)"
                style={{ marginTop: 10, width: "100%", padding: 10, borderRadius: 12, border: "1px solid rgba(255,255,255,.2)", background: "rgba(0,0,0,.25)", color: "inherit" }} />}
              {reviewed[sel.id] && <p className="muted" style={{ color: "#2ee6a6" }}>Recorded: {reviewed[sel.id]}</p>}
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
