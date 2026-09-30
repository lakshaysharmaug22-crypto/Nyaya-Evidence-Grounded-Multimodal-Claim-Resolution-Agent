"use client";
import { useCallback, useEffect, useState } from "react";
import { Glass } from "@/components/Glass";
import { FlowGraph } from "@/components/FlowGraph";
import { BriefView } from "@/components/BriefView";
import { AgentSearch } from "@/components/AgentSearch";
import { API, Final, useClaimStream } from "@/lib/useClaimStream";
import { agentFetch, downloadFromApi } from "@/lib/agent";
import { Item, QUEUE } from "@/lib/queue";
import { DemoBar, useDemo } from "@/components/DemoBar";

const post = (path: string, body?: unknown) =>
  API ? agentFetch(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }).catch(() => null) : Promise.resolve(null);

const REPLY_STATUS: Record<string, string> = {
  sent: "Delivered.",
  dry_run: "Recorded, not sent: the API is in dry-run mode.",
  destination_not_allowed: "Recorded, not sent: destination is not on the allowlist.",
  failed: "Delivery failed. Nothing was sent; try again.",
  demo: "Demo mode: no API connected.",
};

function downloadCsv(id: string, f: Final) {
  const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const rows = [["id", "decision", "rule", "lane", "ms", "verified", "trace"],
    [id, f.final.decision, f.final.rule, f.final.lane, f.ms, f.verified, JSON.stringify(f.trace ?? [])]];
  const blob = new Blob([rows.map((r) => r.map(esc).join(",")).join("\n")], { type: "text/csv" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${id}-audit.csv`; a.click();
}

type CaseData = {
  run: { id: string; decision: string; rule: string; lane: string; text: string; order_id?: string; evidence: Record<string, unknown>;
    trace: { tool: string; attempt: number; ok: boolean }[]; draft_reply?: string; brief?: import("@/components/BriefView").Brief["brief"] & { } | null;
    llm_used?: boolean; cost_inr?: number; groundedness?: number | null };
  decisions: { action: string; reason: string }[]; handoffs: string[];
};

/** Read-only view of any logged case, opened from search. */
function CaseCard({ id, onClose }: { id: string; onClose: () => void }) {
  const [d, setD] = useState<CaseData | null>(null);
  const [err, setErr] = useState("");
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    setErr(""); setD(null);
    try {
      const r = await agentFetch(`/cases/${encodeURIComponent(id)}`);
      if (r.status === 404) return setErr("No logged run for this claim yet.");
      if (!r.ok) return setErr("Could not load this case.");
      setD(await r.json());
    } catch { setErr("Could not reach the server."); }
  }, [id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { window.addEventListener("agent-token-set", load); return () => window.removeEventListener("agent-token-set", load); }, [load]);

  const decide = async (action: "approve" | "reject") => {
    if (action === "reject" && !rejecting) return setRejecting(true);
    if (action === "reject" && !reason.trim()) return;
    const r = await agentFetch("/decisions", { method: "POST", body: JSON.stringify({ id, action, reason }) });
    setNote(r.ok ? `Recorded: ${action}${reason ? ` (${reason})` : ""}` : "Could not save the decision."); setRejecting(false); load();
  };
  const run = d?.run;
  return (
    <Glass solid style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <h2>Case {id}</h2><button className="pill" style={{ background: "transparent", color: "inherit", cursor: "pointer" }} onClick={onClose}>Close</button>
      </div>
      {err && <p style={{ color: "#ff8a8a" }}>{err}</p>}
      {!d && !err && <p className="muted">Loading...</p>}
      {run && (
        <>
          <div><b style={{ textTransform: "capitalize" }}>{run.decision}</b> · rule {run.rule} · {run.lane} lane · order {run.order_id}</div>
          <p className="muted">“{run.text}”</p>
          <table style={{ fontSize: 13, borderCollapse: "collapse", margin: "8px 0" }}><tbody>
            {Object.entries(run.evidence).filter(([, v]) => v !== null && typeof v !== "object").map(([k, v]) => (
              <tr key={k}><td style={{ opacity: .65, paddingRight: 16 }}>{k.replace(/_/g, " ")}</td><td>{String(v)}</td></tr>))}
          </tbody></table>
          {run.brief && <BriefView b={{ llm_used: !!run.llm_used, cost_inr: run.cost_inr ?? 0, groundedness: run.groundedness, brief: run.brief }} />}
          <div className="muted" style={{ marginTop: 8 }}>Tools: {run.trace.map((t) => `${t.tool}${t.ok ? "" : " (failed, retried)"}`).join(" → ")}</div>
          {d!.decisions.map((x, i) => <div key={i} className="muted">Human: {x.action}{x.reason && ` — ${x.reason}`}</div>)}
          {d!.handoffs.map((h, i) => <div key={i} className="muted" style={{ color: "#ffb454" }}>Customer asked for a person{h && `: “${h}”`}</div>)}
          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            <button className="btn go" onClick={() => decide("approve")}>Approve</button>
            <button className="btn no" onClick={() => decide("reject")}>{rejecting ? "Confirm reject" : "Reject"}</button>
            <button className="btn" style={{ background: "rgba(255,255,255,.14)" }} onClick={() => downloadFromApi(`/audit/${encodeURIComponent(id)}.csv`, `${id}-audit.csv`)}>Export CSV</button>
          </div>
          {rejecting && <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason required"
            style={{ marginTop: 10, width: "100%", padding: 10, borderRadius: 12, border: "1px solid rgba(255,255,255,.2)", background: "rgba(0,0,0,.25)", color: "inherit" }} />}
          {note && <p className="muted" style={{ color: "#2ee6a6" }}>{note}</p>}
        </>
      )}
    </Glass>
  );
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
  const [sent, setSent] = useState<Record<string, string>>({});
  const [replyTo, setReplyTo] = useState<Record<string, string>>({});
  const [analysing, setAnalysing] = useState(false);
  const [opened, setOpened] = useState<string | null>(null);
  const [stuck, setStuck] = useState<{ id: string }[]>([]);

  const res = results[sel.id];
  const ready = QUEUE.filter((q) => results[q.id]?.final.lane === "ready" && !reviewed[q.id]);

  // open a case from search (?claim=ID or the open-case event)
  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("claim");
    if (fromUrl) setOpened(fromUrl);
    const h = (e: Event) => setOpened((e as CustomEvent<string>).detail);
    window.addEventListener("open-case", h); return () => window.removeEventListener("open-case", h);
  }, []);
  const inQueue = opened ? QUEUE.find((q) => q.id === opened) : undefined;
  useEffect(() => { if (inQueue) setSel(inQueue); }, [inQueue]);

  // runs that stopped mid-way (crash / restart) and can be resumed
  const loadStuck = useCallback(async () => {
    if (!API) return;
    try { const r = await agentFetch("/recoverable"); if (r.ok) setStuck(await r.json()); } catch { /* offline */ }
  }, []);
  useEffect(() => { loadStuck(); window.addEventListener("agent-token-set", loadStuck); return () => window.removeEventListener("agent-token-set", loadStuck); }, [loadStuck]);
  const resume = async (id: string) => { await agentFetch(`/claims/${encodeURIComponent(id)}/resume`, { method: "POST" }); loadStuck(); setOpened(id); };

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
    // Clicking Send is the agent's approval of this exact text. The API still refuses non-allowlisted
    // destinations and sends nothing while REPLY_MODE is dry_run.
    const r = await post("/replies", { id: sel.id, text: drafts[sel.id], to: replyTo[sel.id] || undefined,
                                       approved: true, reply_id: `${sel.id}:${(drafts[sel.id] ?? "").length}` });
    const j = r && r.ok ? await r.json().catch(() => null) : null;
    setSent((s) => ({ ...s, [sel.id]: j?.status ?? (API ? "failed" : "demo") }));
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
      <p className="muted">Ready lane: approve in one tap. Review lane: needs a human look. Press A to approve, R to reject, / to search.</p>
      <AgentSearch />
      {stuck.length > 0 && (
        <Glass solid style={{ marginBottom: 16 }}>
          <b>{stuck.length} run{stuck.length > 1 ? "s" : ""} stopped mid-way.</b>{" "}
          {stuck.slice(0, 5).map((s) => <button key={s.id} className="pill" style={{ background: "transparent", color: "inherit", cursor: "pointer", marginRight: 6 }} onClick={() => resume(s.id)}>Resume {s.id}</button>)}
        </Glass>
      )}
      {opened && !inQueue && <CaseCard id={opened} onClose={() => setOpened(null)} />}
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
              {res.brief && <BriefView b={res.brief} />}
              <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                <button className="btn go" onClick={approve}>Approve (A)</button>
                <button className="btn no" onClick={reject}>{rejecting ? "Confirm reject" : "Reject (R)"}</button>
                <button className="btn" style={{ background: "rgba(255,255,255,.14)" }}
                  onClick={() => API ? downloadFromApi(`/audit/${sel.id}.csv`, `${sel.id}-audit.csv`) : downloadCsv(sel.id, res)}>Export CSV</button>
              </div>
              {rejecting && <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason required (saved to the override set)"
                style={{ marginTop: 10, width: "100%", padding: 10, borderRadius: 12, border: "1px solid rgba(255,255,255,.2)", background: "rgba(0,0,0,.25)", color: "inherit" }} />}
              {reviewed[sel.id] && <p className="muted" style={{ color: "#2ee6a6" }}>Recorded: {reviewed[sel.id]}</p>}
              <div className="muted" style={{ marginTop: 14 }}>Reply to customer (editable)</div>
              <textarea value={drafts[sel.id] ?? ""} onChange={(e) => setDrafts((d) => ({ ...d, [sel.id]: e.target.value }))} />
              <input value={replyTo[sel.id] ?? ""} onChange={(e) => setReplyTo((t) => ({ ...t, [sel.id]: e.target.value }))}
                placeholder="Customer email or phone (must be allowlisted)" aria-label="Reply destination"
                style={{ width: "100%", marginTop: 8, padding: 10, borderRadius: 12, border: "1px solid rgba(255,255,255,.2)", background: "rgba(0,0,0,.25)", color: "inherit" }} />
              <button className="btn go" style={{ marginTop: 8 }} disabled={sent[sel.id] === "sent"} onClick={sendReply}>
                {sent[sel.id] === "sent" ? "Sent" : "Approve and send"}</button>
              {sent[sel.id] && <span className="muted"> {REPLY_STATUS[sent[sel.id]] ?? sent[sel.id]}</span>}
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
