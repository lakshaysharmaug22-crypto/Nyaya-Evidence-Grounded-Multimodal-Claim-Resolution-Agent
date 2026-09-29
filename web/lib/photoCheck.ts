"use client";
/** Client-side photo quality check (blur, brightness, size) so users get instant feedback before upload. */
export type Quality = { ok: boolean; reason: string; tip: string; brightness: number; sharpness: number };

export async function checkPhoto(file: File): Promise<Quality> {
  const bmp = await createImageBitmap(file);
  const w = 512, h = Math.max(1, Math.round((bmp.height * w) / bmp.width));
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  const ctx = c.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(bmp, 0, 0, w, h);
  const d = ctx.getImageData(0, 0, w, h).data;
  const g = new Float32Array(w * h);
  let sum = 0;
  for (let i = 0; i < w * h; i++) { g[i] = 0.299 * d[i * 4] + 0.587 * d[i * 4 + 1] + 0.114 * d[i * 4 + 2]; sum += g[i]; }
  const brightness = sum / (w * h);
  let m = 0, m2 = 0, n = 0;
  for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
    const i = y * w + x, l = -4 * g[i] + g[i - 1] + g[i + 1] + g[i - w] + g[i + w];
    m += l; m2 += l * l; n++;
  }
  const sharpness = m2 / n - (m / n) ** 2;
  const base = { brightness: Math.round(brightness), sharpness: Math.round(sharpness) };
  if (Math.min(bmp.width, bmp.height) < 320) return { ok: false, reason: "too_small", tip: "Move closer or use a higher-resolution photo.", ...base };
  if (brightness < 45) return { ok: false, reason: "too_dark", tip: "Turn on a light and retake.", ...base };
  if (brightness > 225) return { ok: false, reason: "overexposed", tip: "Avoid glare and retake.", ...base };
  if (sharpness < 150) return { ok: false, reason: "blurry", tip: "Hold steady and tap to focus on the damage.", ...base };
  return { ok: true, reason: "ok", tip: "Looks good.", ...base };
}
