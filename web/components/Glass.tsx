"use client";
import { useAdaptiveTint } from "@/lib/useAdaptiveTint";
import { useBg } from "./Background";

export function Glass({ children, className = "", style, solid = false, press = false }:
  { children: React.ReactNode; className?: string; style?: React.CSSProperties; solid?: boolean; press?: boolean }) {
  const el = useAdaptiveTint(useBg(), solid ? 0.55 : 0);
  return (
    <div ref={el} className={`glass ${press ? "press" : ""} ${className}`} style={{ padding: 18, ...style }}>
      {children}
    </div>
  );
}
