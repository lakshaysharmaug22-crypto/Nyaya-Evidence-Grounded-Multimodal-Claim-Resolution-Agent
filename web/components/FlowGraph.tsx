"use client";
export const NODES = [
  ["photo", "Photo analysis (CNN)"],
  ["invoice", "Invoice parse (OCR)"],
  ["order", "Order lookup (tool)"],
  ["classify", "Claim type + cluster"],
  ["fuse", "Cross-modal fusion + policy"],
  ["act", "Action (refund / hold)"],
  ["verify", "Resolution verification"],
] as const;

export type Status = Record<string, "running" | "done" | undefined>;

export function FlowGraph({ status }: { status: Status }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "stretch" }}>
      {NODES.map(([id, label], i) => (
        <div key={id}>
          <div className={`node ${status[id] ?? ""}`}>{label}</div>
          {i < NODES.length - 1 && <div className={`edge ${status[id] === "done" ? "on" : ""}`} />}
        </div>
      ))}
    </div>
  );
}
