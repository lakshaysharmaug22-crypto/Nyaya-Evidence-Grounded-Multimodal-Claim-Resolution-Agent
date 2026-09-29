"""ONNX damage inference. Falls back to a neutral score if the model file is absent."""
from pathlib import Path

import numpy as np
from PIL import Image

MODEL = Path(__file__).parent / "artifacts" / "damage.int8.onnx"
MEAN, STD = np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225])
_sess = None


def _session():
    global _sess
    if _sess is None and MODEL.exists():
        import onnxruntime as ort
        _sess = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    return _sess


def damage_confidence(img: Image.Image, damaged_index: int = 0) -> float:
    s = _session()
    if s is None:
        return 0.0
    im = img.convert("RGB").resize((256, 256)).crop((16, 16, 240, 240))
    x = ((np.asarray(im, dtype=np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)
    z = s.run(None, {"x": x})[0][0]
    e = np.exp(z - z.max())
    return float((e / e.sum())[damaged_index])
