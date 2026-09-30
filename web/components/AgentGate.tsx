"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Glass } from "./Glass";
import { isSample, setSample, setToken } from "@/lib/agent";

/** Appears only when an agent-only endpoint answers 401. Customers never see it.
 *  Visitors without a token can explore the agent pages on built-in sample data instead. */
export function AgentGate() {
  const [show, setShow] = useState(false);
  const [sample, setSampleState] = useState(false);
  const [v, setV] = useState("");
  const path = usePathname();
  const agentPage = path?.startsWith("/console") || path?.startsWith("/insights");

  useEffect(() => {
    const on = () => { if (!isSample()) setShow(true); };
    const off = () => setShow(false);
    const s = () => setSampleState(isSample());
    s();
    window.addEventListener("agent-401", on); window.addEventListener("agent-token-set", off);
    window.addEventListener("agent-sample", s);
    return () => {
      window.removeEventListener("agent-401", on); window.removeEventListener("agent-token-set", off);
      window.removeEventListener("agent-sample", s);
    };
  }, []);

  const input = { width: "100%", padding: 12, borderRadius: 12, border: "1px solid rgba(255,255,255,.2)", background: "rgba(0,0,0,.25)", color: "inherit" } as const;

  return (
    <>
      {sample && agentPage && (
        <div role="status" style={{ position: "fixed", top: 12, left: "50%", transform: "translateX(-50%)", zIndex: 40,
          padding: "8px 14px", borderRadius: 999, background: "rgba(20,24,34,.72)", backdropFilter: "blur(14px)",
          border: "1px solid rgba(255,255,255,.18)", fontSize: 13, display: "flex", gap: 10, alignItems: "center", whiteSpace: "nowrap" }}>
          <span>Sample data. Nothing reaches the live API</span>
          <button className="pill" style={{ background: "rgba(255,255,255,.14)", color: "inherit", cursor: "pointer" }}
            onClick={() => setSample(false)}>Use agent token</button>
        </div>
      )}
      {show && (
        <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "grid", placeItems: "center", background: "rgba(0,0,0,.5)" }}>
          <div style={{ width: "min(92vw, 400px)" }}>
            <Glass solid>
              <h2>Agent access</h2>
              <p className="muted">This area is for support agents. Enter the access token, or explore the console with sample data.</p>
              <input type="password" value={v} onChange={(e) => setV(e.target.value)} autoFocus aria-label="Agent access token"
                onKeyDown={(e) => e.key === "Enter" && v && setToken(v)} style={input} />
              <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                <button className="btn go" disabled={!v} onClick={() => setToken(v)}>Continue</button>
                <button className="btn" style={{ background: "rgba(255,255,255,.14)" }}
                  onClick={() => { setShow(false); setSample(true); }}>Explore with sample data</button>
              </div>
            </Glass>
          </div>
        </div>
      )}
    </>
  );
}
