"use client";
import { useEffect, useMemo, useState } from "react";
import { Glass } from "@/components/Glass";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

// Deterministic sample cases so the simulator is never empty. Replace with real logged cases.
function sample(n = 100) {
  let s = 42; const r = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  return Array.from({ length: n }, () => {
    const truth = r() < 0.72;
    const conf = Math.min(0.99, Math.max(0.3, truth ? 0.72 + r() * 0.27 : 0.35 + r() * 0.5));
    return { conf, amount: [499, 999, 1499, 2999, 5999, 8999][Math.floor(r() * 6)], truth };
  });
}
const CURRENT = { minConf: 0.9, maxAmt: 5000 };
type M = { n: number; auto_resolve_rate?: number; verified_rate?: number; p95_ms?: number; recovered?: number };

export default function Insights() {
  const cases = useMemo(() => sample(), []);
  const [minConf, setMinConf] = useState(CURRENT.minConf);
  const [maxAmt, setMaxAmt] = useState(CURRENT.maxAmt);
  const [m, setM] = useState<M | null>(null);

  useEffect(() => {
    if (!API) return;
    fetch(`${API}/metrics`).then((r) => r.json()).then(setM).catch(() => setM(null));
  }, []);

  const sim = (c: number, a: number) => {
    const auto = cases.filter((x) => x.conf >= c && x.amount <= a);
    return { auto: auto.length, wrong: auto.filter((x) => !x.truth).length };
  };
  const cur = sim(CURRENT.minConf, CURRENT.maxAmt), now = sim(minConf, maxAmt);
  const live = m && m.n > 0;
  const tiles: [string, string][] = live
    ? [["Runs", String(m!.n)], ["Auto-resolve", `${Math.round((m!.auto_resolve_rate ?? 0) * 100)}%`],
       ["Verified", `${Math.round((m!.verified_rate ?? 0) * 100)}%`], ["p95 latency", `${m!.p95_ms} ms`], ["Recovered failures", String(m!.recovered ?? 0)]]
    : [["Runs", "sample"], ["Auto-resolve", `${cur.auto}%`], ["Wrong approvals", `${cur.wrong}`], ["p95 latency", "n/a"], ["Recovered failures", "n/a"]];

  return (
    <div className="wrap" style={{ maxWidth: 1000 }}>
      <h1>Insights</h1>
      <p className="muted">{live ? "Live metrics from the running API." : "Sample data. Connect the API to see live runs."}</p>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", marginBottom: 16 }}>
        {tiles.map(([k, v]) => (
          <Glass key={k}><div className="muted">{k}</div><div style={{ fontSize: 26, fontWeight: 700 }}>{v}</div></Glass>
        ))}
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
