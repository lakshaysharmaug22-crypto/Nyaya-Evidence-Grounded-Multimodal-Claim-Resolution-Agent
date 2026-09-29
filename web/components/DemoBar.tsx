"use client";
import { useEffect, useState } from "react";
import { Glass } from "./Glass";
import type { LogEv, TraceEv } from "@/lib/useClaimStream";

export function useDemo() {
  const [demo, setDemo] = useState(false);
  useEffect(() => setDemo(new URLSearchParams(window.location.search).get("demo") === "1"), []);
  return demo;
}

/** Interviewer tools: inject a tool failure, then scrub through the recorded run. */
export function DemoBar({ inject, setInject, log, trace }:
  { inject: boolean; setInject: (v: boolean) => void; log: LogEv[]; trace?: TraceEv[] }) {
  const [i, setI] = useState(0);
  useEffect(() => setI(log.length), [log.length]);
  const ev = log[Math.min(i, log.length) - 1];
  return (
    <Glass solid style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
        <b>Demo mode</b>
        <label style={{ cursor: "pointer" }}>
          <input type="checkbox" checked={inject} onChange={(e) => setInject(e.target.checked)} /> Inject failure (order lookup)
        </label>
        <label className="muted">Replay
          <input type="range" min={0} max={log.length} value={i} disabled={!log.length}
            onChange={(e) => setI(Number(e.target.value))} style={{ marginLeft: 8, verticalAlign: "middle" }} />
        </label>
        <span className="muted">{ev ? `step ${i}/${log.length}: ${ev.node} ${ev.status}` : "no run yet"}</span>
      </div>
      {trace && trace.some((t) => !t.ok) && (
        <div className="muted" style={{ marginTop: 10, color: "#2ee6a6" }}>
          Recovered: {trace.map((t) => `${t.tool} attempt ${t.attempt} ${t.ok ? "ok" : "failed"}`).join(" → ")}
        </div>
      )}
    </Glass>
  );
}
