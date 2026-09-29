"use client";
import { useEffect, useMemo, useState } from "react";
import { Glass } from "@/components/Glass";

import { API } from "@/lib/useClaimStream";
import { agentFetch } from "@/lib/agent";
import { AgentSearch } from "@/components/AgentSearch";

// Deterministic sample cases so the simulator is never empty. Replace with real logged cases.
function sample(n = 100) {
  let s = 42; const r = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  return Array.from({ length: n }, () => {
    const truth = r() < 0.72;
    const conf = Math.min(0.99, Math.max(0.3, truth ? 0.72 + r() * 0.27 : 0.35 + r() * 0.5));
    return { conf, amount: [499, 999, 1499, 2999, 5999, 8999][Math.floor(r() * 6)], truth };
  });
}
// Same rules as agent/drift.py, run on a sample series so the panel works without the API.
type R = { lane: string; decision: string; ms: number; verified: boolean };
function stats(rs: R[]) {
  const n = rs.length, lat = rs.map((r) => r.ms).sort((a, b) => a - b);
  return { auto: rs.filter((r) => r.lane === "ready").length / n, esc: rs.filter((r) => r.decision === "escalate").length / n,
    ver: rs.filter((r) => r.verified).length / n, p95: lat[Math.floor(0.95 * (n - 1))] };
}
function driftCheck(runs: R[], w = 20): { metric: string; ref: number; now: number }[] {
  const ref = stats(runs.slice(-2 * w, -w)), cur = stats(runs.slice(-w)), out = [];
  if (cur.auto < ref.auto - 0.15) out.push({ metric: "auto-resolve rate", ref: ref.auto, now: cur.auto });
  if (cur.esc > ref.esc + 0.2) out.push({ metric: "escalation rate", ref: ref.esc, now: cur.esc });
  if (cur.ver < 0.95) out.push({ metric: "verified rate", ref: ref.ver, now: cur.ver });
  if (cur.p95 > ref.p95 * 1.5 + 5) out.push({ metric: "p95 latency (ms)", ref: ref.p95, now: cur.p95 });
  return out;
}
const series = (degraded: boolean): R[] => Array.from({ length: 40 }, (_, i) =>
  i >= 20 && degraded ? { lane: "review", decision: "escalate", ms: 40, verified: true } : { lane: "ready", decision: "approve", ms: 6, verified: true });
const SAMPLE_CLUSTERS = [
  { terms: ["wrong", "different", "debited"], count: 14 }, { terms: ["arrived", "weeks", "late"], count: 9 },
  { terms: ["charger", "included", "box"], count: 6 }, { terms: ["match", "listing"], count: 5 }];
const fmt = (metric: string, v: number) => (metric.includes("p95") ? `${Math.round(v * 10) / 10} ms` : `${Math.round(v * 100)}%`);
const CURRENT = { minConf: 0.9, maxAmt: 5000 };
type M = { n: number; auto_resolve_rate?: number; verified_rate?: number; p95_ms?: number; recovered?: number; llm_routed_rate?: number; avg_cost_inr?: number; groundedness?: number | null };

export default function Insights() {
  const cases = useMemo(() => sample(), []);
  const [minConf, setMinConf] = useState(CURRENT.minConf);
  const [maxAmt, setMaxAmt] = useState(CURRENT.maxAmt);
  const [m, setM] = useState<M | null>(null);
  const [degraded, setDegraded] = useState(false);
  const [liveDrift, setLiveDrift] = useState<{ status: string; alerts: { metric: string; ref: number; now: number }[] } | null>(null);
  const [liveClusters, setLiveClusters] = useState<{ terms: string[]; count: number }[] | null>(null);

  useEffect(() => {
    if (!API) return;
    const load = () => {
      const get = (path: string) => agentFetch(path).then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); });
      get("/metrics").then(setM).catch(() => setM(null));
      get("/drift").then(setLiveDrift).catch(() => setLiveDrift(null));
      get("/clusters").then(setLiveClusters).catch(() => setLiveClusters(null));
    };
    load();
    window.addEventListener("agent-token-set", load);
    return () => window.removeEventListener("agent-token-set", load);
  }, []);

  const sim = (c: number, a: number) => {
    const auto = cases.filter((x) => x.conf >= c && x.amount <= a);
    return { auto: auto.length, wrong: auto.filter((x) => !x.truth).length };
  };
  const cur = sim(CURRENT.minConf, CURRENT.maxAmt), now = sim(minConf, maxAmt);
  const live = m && m.n > 0;
  const useLiveDrift = liveDrift && liveDrift.status !== "insufficient_data";
  const alerts = useLiveDrift ? liveDrift!.alerts : driftCheck(series(degraded));
  const clusters = liveClusters && liveClusters.length ? liveClusters : SAMPLE_CLUSTERS;
  const maxC = Math.max(...clusters.map((c) => c.count));
  const tiles: [string, string][] = live
    ? [["Runs", String(m!.n)], ["Auto-resolve", `${Math.round((m!.auto_resolve_rate ?? 0) * 100)}%`],
       ["Verified", `${Math.round((m!.verified_rate ?? 0) * 100)}%`], ["p95 latency", `${m!.p95_ms} ms`], ["Recovered failures", String(m!.recovered ?? 0)],
       ["Sent to AI", `${Math.round((m!.llm_routed_rate ?? 0) * 100)}%`], ["Avg cost / case", `₹${(m!.avg_cost_inr ?? 0).toFixed(3)}`],
       ["Findings verified", m!.groundedness == null ? "n/a" : `${Math.round(m!.groundedness * 100)}%`]]
    : [["Runs", "sample"], ["Auto-resolve", `${cur.auto}%`], ["Wrong approvals", `${cur.wrong}`], ["p95 latency", "n/a"], ["Recovered failures", "n/a"]];

  return (
    <div className="wrap" style={{ maxWidth: 1000 }}>
      <h1>Insights</h1>
      <AgentSearch />
      <p className="muted">{live ? "Live metrics from the running API." : "Sample data. Connect the API to see live runs."}</p>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", marginBottom: 16 }}>
        {tiles.map(([k, v]) => (
          <Glass key={k}><div className="muted">{k}</div><div style={{ fontSize: 26, fontWeight: 700 }}>{v}</div></Glass>
        ))}
      </div>
      <div className="grid two" style={{ marginBottom: 16 }}>
        <Glass>
          <h2>Drift alerts {useLiveDrift ? "" : "(sample series)"}</h2>
          {!useLiveDrift && (
            <label className="muted" style={{ cursor: "pointer" }}>
              <input type="checkbox" checked={degraded} onChange={(e) => setDegraded(e.target.checked)} /> Simulate a degraded model
            </label>
          )}
          {alerts.length === 0 ? <p style={{ color: "#2ee6a6" }}>All metrics within range.</p> : alerts.map((a) => (
            <p key={a.metric} style={{ color: "#ff8a8a", margin: "8px 0" }}>
              {a.metric}: {fmt(a.metric, a.ref)} → {fmt(a.metric, a.now)}
            </p>
          ))}
        </Glass>
        <Glass>
          <h2>Failure clusters {liveClusters && liveClusters.length ? "" : "(sample)"}</h2>
          {clusters.map((c) => (
            <div key={c.terms.join()} style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}><span>{c.terms.join(" · ")}</span><b>{c.count}</b></div>
              <div style={{ height: 6, borderRadius: 3, background: "rgba(255,255,255,.12)" }}>
                <div style={{ height: 6, borderRadius: 3, width: `${(c.count / maxC) * 100}%`, background: "linear-gradient(90deg,#1aa3ff,#2ee6a6)" }} />
              </div>
            </div>
          ))}
        </Glass>
      </div>
      <Glass solid>
        <h2>Policy simulator (replays {cases.length} sample cases)</h2>
        <label style={{ display: "block", marginBottom: 12 }}>Min damage confidence: <b>{minConf.toFixed(2)}</b>
          <input type="range" min={0.5} max={0.99} step={0.01} value={minConf} onChange={(e) => setMinConf(+e.target.value)} style={{ width: "100%" }} />
        </label>
        <label style={{ display: "block", marginBottom: 12 }}>Max auto-approve amount: <b>₹{maxAmt}</b>
          <input type="range" min={500} max={10000} step={500} value={maxAmt} onChange={(e) => setMaxAmt(+e.target.value)} style={{ width: "100%" }} />
        </label>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <div>Auto-approved: <b>{now.auto}</b> <span className="muted">({now.auto - cur.auto >= 0 ? "+" : ""}{now.auto - cur.auto} vs current)</span></div>
          <div>Wrong approvals: <b style={{ color: now.wrong > cur.wrong ? "#ff8a8a" : "#2ee6a6" }}>{now.wrong}</b> <span className="muted">({now.wrong - cur.wrong >= 0 ? "+" : ""}{now.wrong - cur.wrong})</span></div>
        </div>
        <p className="muted">Change a rule, see the effect on past cases before publishing it.</p>
      </Glass>
    </div>
  );
}
