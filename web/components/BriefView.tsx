"use client";
export type Finding = { statement: string; source: string; quote: string };
export type Brief = {
  llm_used: boolean; error?: string | null; cost_inr: number; groundedness?: number | null;
  brief: { summary: string; findings: Finding[]; suggested_action: string; confidence: number };
};

const COLOR: Record<string, string> = { claim_text: "#1aa3ff", invoice: "#ffb454", photo: "#c58bff", order: "#2ee6a6", history: "#ff8a8a" };

/** Reviewer brief. Every finding shows the exact words it was checked against (citation chip). */
export function BriefView({ b }: { b: Brief }) {
  return (
    <div style={{ marginTop: 12 }}>
      <div className="muted">{b.llm_used ? "AI brief (advisory, checked against the sources)" : "Automatic brief (no AI model used)"}</div>
      <div style={{ margin: "6px 0" }}>{b.brief.summary}</div>
      {b.brief.findings.map((f, i) => (
        <div key={i} style={{ margin: "6px 0", fontSize: 13 }}>
          {f.statement}{" "}
          <span title={`Quoted from ${f.source}`} className="pill" style={{ borderColor: COLOR[f.source] ?? "#888", color: COLOR[f.source] }}>
            {f.source.replace("_", " ")}: “{f.quote}”
          </span>
        </div>
      ))}
      {b.llm_used && <div className="muted">
        Model suggests: {b.brief.suggested_action} · the policy engine decides · cost ₹{b.cost_inr.toFixed(3)}
        {b.groundedness != null && ` · ${Math.round(b.groundedness * 100)}% of findings verified`}
      </div>}
      {b.error && <div className="muted" style={{ color: "#ffb454" }}>AI unavailable ({b.error.slice(0, 60)}). Automatic brief shown.</div>}
    </div>
  );
}
