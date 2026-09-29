"use client";
import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Glass } from "./Glass";
import { API } from "@/lib/useClaimStream";
import { agentFetch, openCase } from "@/lib/agent";
import { QUEUE } from "@/lib/queue";

type Hit = { kind: string; id: string; order_id: string; decision: string; rule: string; claim_type: string; snippet: string };
const DEC: Record<string, string> = { approve: "#2ee6a6", escalate: "#ffb454", reject: "#ff8a8a" };

function Snippet({ s }: { s: string }) {
  return <>{s.split(/(\x01[^\x02]*\x02)/).map((p, i) =>
    p.startsWith("\x01") ? <mark key={i} style={{ background: "rgba(26,163,255,.35)", color: "inherit", borderRadius: 4 }}>{p.slice(1, -1)}</mark> : <span key={i}>{p}</span>)}</>;
}

// No API (static demo): search the sample queue in the browser.
function localSearch(q: string): Hit[] {
  const words = q.toLowerCase().split(/\s+/).filter((w) => w && !w.includes(":"));
  return QUEUE.filter((i) => words.every((w) => [i.id, String(i.claim.order_id), i.who, String(i.claim.text)].join(" ").toLowerCase().includes(w)))
    .map((i) => ({ kind: "claim", id: i.id, order_id: String(i.claim.order_id), decision: "", rule: "", claim_type: "", snippet: String(i.claim.text) }));
}

export function AgentSearch() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [idx, setIdx] = useState(0);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const seq = useRef(0);
  const router = useRouter(), path = usePathname();

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const typing = ["INPUT", "TEXTAREA"].includes((e.target as HTMLElement).tagName);
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((o) => !o); }
      else if (e.key === "/" && !typing && !open) { e.preventDefault(); setOpen(true); }
      else if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const mine = ++seq.current;                              // ignore answers that arrive out of order
    setState("loading");
    const t = setTimeout(async () => {
      try {
        if (!API) { setHits(localSearch(q)); setState("idle"); setIdx(0); return; }
        const res = await agentFetch(`/search?q=${encodeURIComponent(q)}`);
        if (!res.ok) throw new Error(String(res.status));
        const body = await res.json();
        if (mine === seq.current) { setHits(body.hits); setIdx(0); setState("idle"); }
      } catch { if (mine === seq.current) setState("error"); }
    }, 180);
    return () => clearTimeout(t);
  }, [q, open]);

  const choose = (h: Hit) => {
    setOpen(false);
    if (path !== "/console") router.push(`/console?claim=${encodeURIComponent(h.id)}`); else openCase(h.id);
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(i + 1, hits.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
    if (e.key === "Enter" && hits[idx]) choose(hits[idx]);
  };

  return (
    <>
      <button className="pill" onClick={() => setOpen(true)} style={{ background: "transparent", color: "inherit", cursor: "pointer", marginBottom: 12 }}>
        Search claims · Ctrl/⌘ K
      </button>
      {open && (
        <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 40, background: "rgba(0,0,0,.55)", display: "flex", justifyContent: "center", alignItems: "flex-start", paddingTop: "10vh" }}>
          <div onClick={(e) => e.stopPropagation()} style={{ width: "min(94vw, 640px)" }}>
            <Glass solid style={{ padding: 12 }}>
              <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey} placeholder="Claim ID, order ID, words from the claim..."
                aria-label="Search claims" style={{ width: "100%", padding: 12, fontSize: 16, borderRadius: 14, border: "1px solid rgba(255,255,255,.2)", background: "rgba(0,0,0,.25)", color: "inherit" }} />
              <div className="muted" style={{ margin: "8px 4px" }}>Try: ORD1002 · crushed · decision:escalate · type:damaged · kind:handoff</div>
              <div style={{ maxHeight: "50vh", overflowY: "auto" }} role="listbox">
                {state === "error" && <div style={{ padding: 10, color: "#ff8a8a" }}>Search is unavailable right now. Check your connection or access token.</div>}
                {state !== "error" && hits.length === 0 && state === "idle" && <div className="muted" style={{ padding: 10 }}>No matches{q ? ` for “${q}”` : ""}.</div>}
                {hits.map((h, i) => (
                  <div key={`${h.kind}-${h.id}-${i}`} role="option" aria-selected={i === idx} onClick={() => choose(h)} onMouseEnter={() => setIdx(i)}
                    style={{ padding: 10, borderRadius: 12, cursor: "pointer", background: i === idx ? "rgba(255,255,255,.16)" : "transparent" }}>
                    <b>{h.id}</b> <span className="pill">{h.kind}</span>{" "}
                    {h.decision && <span className="pill" style={{ color: DEC[h.decision], borderColor: DEC[h.decision] }}>{h.decision}</span>}{" "}
                    {h.rule && <span className="muted">{h.rule}</span>}
                    <div className="muted">{h.order_id && `${h.order_id} · `}<Snippet s={h.snippet} /></div>
                  </div>
                ))}
              </div>
            </Glass>
          </div>
        </div>
      )}
    </>
  );
}
