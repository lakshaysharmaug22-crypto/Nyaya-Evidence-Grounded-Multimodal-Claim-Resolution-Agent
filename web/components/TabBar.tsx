"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Glass } from "./Glass";

export function TabBar() {
  const p = usePathname();
  const tabs = [["/", "Claim"], ["/console", "Console"], ["/insights", "Insights"]];
  return (
    <div className="tabbar">
      <Glass style={{ padding: 6, borderRadius: 999, display: "flex", gap: 6 }}>
        {tabs.map(([href, label]) => (
          <Link key={href} href={href} className={p === href ? "on" : ""} style={{ padding: "10px 18px", borderRadius: 999, fontSize: 14, background: p === href ? "rgba(255,255,255,.18)" : "transparent" }}>{label}</Link>
        ))}
      </Glass>
    </div>
  );
}
