"""ONNX damage inference. Falls back to a neutral score if the model file is absent."""
import hashlib
import logging
import os
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

MODEL = Path(__file__).parent / "artifacts" / "damage.int8.onnx"
MEAN, STD = np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225])
_sess = None
log = logging.getLogger("nyaya.cnn")


def fetch_model() -> bool:
    """Download the INT8 model from CNN_MODEL_URL (e.g. a GitHub release asset) if it is not on disk.

    CNN_MODEL_SHA256 is required: a file that does not match is deleted and the neutral fallback stays on.
    """
    url, want = os.getenv("CNN_MODEL_URL"), (os.getenv("CNN_MODEL_SHA256") or "").lower()
    if MODEL.exists() or not url:
        return MODEL.exists()
    if not url.startswith("https://") or len(want) != 64:
        log.warning("CNN_MODEL_URL needs https and a 64-char CNN_MODEL_SHA256; skipping download")
        return False
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    tmp = MODEL.with_suffix(".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:   # noqa: S310
            f.write(r.read(50 * 1024 * 1024))
        got = hashlib.sha256(tmp.read_bytes()).hexdigest()
        if got != want:
            log.error("CNN model checksum mismatch (got %s); not loading it", got[:12])
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(MODEL)
        return True
    except Exception as e:
        log.error("CNN model download failed: %s", type(e).__name__)
        tmp.unlink(missing_ok=True)
        return False


def _session():
    global _sess
    if _sess is None and not MODEL.exists():
        fetch_model()
    if _sess is None and MODEL.exists():
        import onnxruntime as ort
        _sess = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    return _sess


def damage_confidence(img: Image.Image, damaged_index: int = 0) -> float:
    s = _session()
    if s is None:
        return 0.0
    im = img.convert("RGB")                        # same as training: short side to 256, centre crop 224
    w, h = im.size
    k = 256 / min(w, h)
    im = im.resize((max(224, round(w * k)), max(224, round(h * k))), Image.BILINEAR)
    left, top = (im.width - 224) // 2, (im.height - 224) // 2
    im = im.crop((left, top, left + 224, top + 224))
    x = ((np.asarray(im, dtype=np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)
    z = s.run(None, {"x": x})[0][0]
    e = np.exp(z - z.max())
    return float((e / e.sum())[damaged_index])
