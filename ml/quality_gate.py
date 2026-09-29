"""Cheap pre-upload photo checks: blur, brightness, size. No model, runs in a few ms.

SHARPNESS_MIN is a starting point. Calibrate it on real customer photos
(plot the score for good vs blurry samples and pick the separating value).
"""
import numpy as np
from PIL import Image

SHARPNESS_MIN = 150.0


def sharpness(img: Image.Image) -> float:
    g = img.convert("L")
    w, h = g.size
    g = g.resize((512, max(1, int(h * 512 / w))), Image.LANCZOS)   # scale-normalize
    a = np.asarray(g, dtype=np.float32)
    lap = (-4 * a[1:-1, 1:-1] + a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:])
    return float(lap.var())


def check(img: Image.Image, sharp_min: float = SHARPNESS_MIN) -> dict:
    g = img.convert("L")
    if min(g.size) < 320:
        return {"ok": False, "reason": "too_small", "tip": "Move closer or use a higher-resolution photo."}
    brightness = float(np.asarray(g, dtype=np.float32).mean())
    if brightness < 45:
        return {"ok": False, "reason": "too_dark", "tip": "Turn on a light and retake."}
    if brightness > 225:
        return {"ok": False, "reason": "overexposed", "tip": "Avoid direct glare and retake."}
    s = sharpness(img)
    if s < sharp_min:
        return {"ok": False, "reason": "blurry", "tip": "Hold steady and tap to focus on the damage.", "sharpness": round(s, 1)}
    return {"ok": True, "reason": "ok", "tip": "", "brightness": round(brightness, 1), "sharpness": round(s, 1)}
