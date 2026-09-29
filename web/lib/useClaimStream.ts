"use client";
import { useCallback, useState } from "react";
import type { Status } from "@/components/FlowGraph";

export type TraceEv = { tool: string; attempt: number; ok: boolean; error?: string };
export type Final = {
  final: { decision: string; rule: string; lane: string }; verified: boolean; ms: number; trace?: TraceEv[];
  draft_reply?: string; evidence?: Record<string, unknown> | null; brief?: import("@/components/BriefView").Brief | null;
};
export type LogEv = { node: string; status: string };

export const API = process.env.NEXT_PUBLIC_API_URL ?? "";
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const PAR = ["photo", "invoice", "order", "classify"];
const SER = ["fuse", "act", "verify"];

/** Streams a claim run. Uses the API when NEXT_PUBLIC_API_URL is set, else a local mock (Vercel-friendly). */
export function useClaimStream() {
  const [status, setStatus] = useState<Status>({});
  const [final, setFinal] = useState<Final | null>(null);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<LogEv[]>([]);
  const [error, setError] = useState<string | null>(null);

  const mark = (node: string, st: "running" | "done") => {
    setStatus((s) => ({ ...s, [node]: st }));
    setLog((l) => [...l, { node, status: st }]);
  };

  const run = useCallback(async (claim: Record<string, unknown>): Promise<Final | null> => {
    setStatus({}); setFinal(null); setLog([]); setError(null); setBusy(true);
    let result: Final | null = null;
    try {
      if (API) {
        const res = await fetch(`${API}/claims/stream`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(claim),
        });
        const reader = res.body!.getReader(), dec = new TextDecoder();
        let buf = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const parts = buf.split("\n\n"); buf = parts.pop()!;
          for (const p of parts) {
            const m = JSON.parse(p.replace(/^data: /, ""));
            if (m.node) mark(m.node, m.status);
            if (m.error) setError(m.resumable ? `${m.error}. A person can resume it from the console.` : m.error);
            if (m.final) { result = m; setFinal(m); }
          }
        }
      } else {
        PAR.forEach((n) => mark(n, "running")); await sleep(600);
        PAR.forEach((n) => mark(n, "done"));
        for (const n of SER) { mark(n, "running"); await sleep(400); mark(n, "done"); }
        const c = claim as { damage_conf?: number; days_since_delivery?: number; inject_failure?: boolean };
        const dec = (c.days_since_delivery ?? 0) > 7 ? ["reject", "outside_window", "review"]
          : (c.damage_conf ?? 0) >= 0.9 ? ["approve", "auto_approve", "ready"] : ["escalate", "low_confidence_or_high_value", "review"];
        const trace: TraceEv[] = c.inject_failure
          ? [{ tool: "order_lookup", attempt: 1, ok: false, error: "order_lookup unavailable" }, { tool: "order_lookup", attempt: 2, ok: true }]
          : [{ tool: "order_lookup", attempt: 1, ok: true }];
        const amt = (claim as { amount_inr?: number }).amount_inr;
        const draft = dec[0] === "approve"
          ? `Hi, regarding claim ${claim.id}: we checked your photo, invoice and order details and approved a refund of ₹${amt?.toLocaleString("en-IN")}. It will reach your original payment method in 5-7 working days.`
          : `Hi, regarding claim ${claim.id}: a team member is reviewing your claim and will update you shortly.`;
        result = { final: { decision: dec[0], rule: dec[1], lane: dec[2] }, verified: true, ms: 2700, trace, draft_reply: draft };
        setFinal(result);
      }
    } finally { setBusy(false); }
    return result;
  }, []);
  return { status, final, busy, run, log, error };
}
