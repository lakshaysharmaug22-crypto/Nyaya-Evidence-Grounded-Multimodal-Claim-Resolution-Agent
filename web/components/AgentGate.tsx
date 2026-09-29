"use client";
import { useEffect, useState } from "react";
import { Glass } from "./Glass";
import { setToken } from "@/lib/agent";

/** Appears only when an agent-only endpoint answers 401. Customers never see it. */
export function AgentGate() {
  const [show, setShow] = useState(false);
  const [v, setV] = useState("");
  useEffect(() => {
    const on = () => setShow(true), off = () => setShow(false);
    window.addEventListener("agent-401", on); window.addEventListener("agent-token-set", off);
    return () => { window.removeEventListener("agent-401", on); window.removeEventListener("agent-token-set", off); };
  }, []);
  if (!show) return null;
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "grid", placeItems: "center", background: "rgba(0,0,0,.5)" }}>
      <div style={{ width: "min(92vw, 380px)" }}>
        <Glass solid>
          <h2>Agent access</h2>
          <p className="muted">This area is for support agents. Enter the access token.</p>
          <input type="password" value={v} onChange={(e) => setV(e.target.value)} autoFocus
            onKeyDown={(e) => e.key === "Enter" && v && setToken(v)}
            style={{ width: "100%", padding: 12, borderRadius: 12, border: "1px solid rgba(255,255,255,.2)", background: "rgba(0,0,0,.25)", color: "inherit" }} />
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button className="btn go" disabled={!v} onClick={() => setToken(v)}>Continue</button>
            <button className="btn" style={{ background: "rgba(255,255,255,.14)" }} onClick={() => setShow(false)}>Cancel</button>
          </div>
        </Glass>
      </div>
    </div>
  );
}
