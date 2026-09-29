"use client";
import { createContext, useContext, useEffect, useRef } from "react";

export const BgCtx = createContext<React.RefObject<HTMLCanvasElement | null> | null>(null);
export const useBg = () => useContext(BgCtx)!;

/** Slow-moving gradient blobs. Canvas is also the sampling source for adaptive tint. */
export function Background({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current!, ctx = c.getContext("2d", { willReadFrequently: true })!;
    c.width = 160; c.height = 240;
    const blobs = [
      { x: .2, y: .2, r: .55, c: "26,163,255", s: .0004 },
      { x: .8, y: .4, r: .5, c: "46,230,166", s: .0003 },
      { x: .5, y: .85, r: .6, c: "150,90,255", s: .00035 },
      { x: .9, y: .9, r: .4, c: "255,200,120", s: .00045 },
    ];
    let raf = 0;
    const draw = (t: number) => {
      ctx.fillStyle = "#07080d"; ctx.fillRect(0, 0, c.width, c.height);
      blobs.forEach((b, i) => {
        const x = (b.x + Math.sin(t * b.s + i) * .18) * c.width;
        const y = (b.y + Math.cos(t * b.s * 1.3 + i) * .15) * c.height;
        const r = b.r * c.width;
        const g = ctx.createRadialGradient(x, y, 0, x, y, r);
        g.addColorStop(0, `rgba(${b.c},.75)`); g.addColorStop(1, `rgba(${b.c},0)`);
        ctx.fillStyle = g; ctx.fillRect(0, 0, c.width, c.height);
      });
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []);
  return (
    <BgCtx.Provider value={ref}>
      <div className="blobs"><canvas ref={ref} /></div>
      {children}
    </BgCtx.Provider>
  );
}
