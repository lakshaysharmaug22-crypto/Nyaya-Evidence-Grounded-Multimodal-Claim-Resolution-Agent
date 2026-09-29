"use client";
import { useEffect, useRef } from "react";

const lum = (r: number, g: number, b: number) => {
  const f = (c: number) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};

/** Samples the canvas behind an element and sets --tint, --tint-a, --text. */
export function useAdaptiveTint(bg: React.RefObject<HTMLCanvasElement | null>, minAlpha = 0) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-transparency: reduce)").matches) return;
    let raf = 0, last = 0, prev = -1;
    const tick = (t: number) => {
      raf = requestAnimationFrame(tick);
      if (t - last < 200 || document.hidden || !bg.current || !el.current) return;
      last = t;
      const c = bg.current, b = el.current.getBoundingClientRect(), cr = c.getBoundingClientRect();
      const sx = c.width / cr.width, sy = c.height / cr.height;
      const x = Math.max(0, Math.min(c.width - 1, (b.left - cr.left) * sx));
      const y = Math.max(0, Math.min(c.height - 1, (b.top - cr.top) * sy));
      const w = Math.max(1, Math.min(c.width - x, b.width * sx));
      const h = Math.max(1, Math.min(c.height - y, b.height * sy));
      const d = c.getContext("2d")!.getImageData(x, y, w, h).data;
      let s = 0, n = 0;
      for (let i = 0; i < d.length; i += 16) { s += lum(d[i], d[i + 1], d[i + 2]); n++; }
      const L = s / n;
      if (Math.abs(L - prev) < 0.03) return;
      prev = L;
      const bright = L > 0.45;
      const st = el.current.style;
      st.setProperty("--tint", bright ? "16,18,26" : "255,255,255");
      st.setProperty("--tint-a", String(Math.max(minAlpha, bright ? 0.3 + L * 0.25 : 0.1 + (1 - L) * 0.08)));
      st.setProperty("--text", bright ? "#fff" : "#0b0d14");
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [bg, minAlpha]);
  return el;
}
