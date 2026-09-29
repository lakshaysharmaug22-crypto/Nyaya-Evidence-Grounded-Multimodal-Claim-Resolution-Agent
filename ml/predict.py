"""Runtime predictions from the trained tabular models. Returns None-safe fallbacks if artifacts are missing."""
from pathlib import Path

import joblib
import numpy as np

from .synth import TYPES

PATH = Path(__file__).parent / "artifacts" / "tabular.joblib"
_m = None


def _load():
    global _m
    if _m is None and PATH.exists():
        _m = joblib.load(PATH)
    return _m


def classify(text: str) -> dict:
    m = _load()
    if not m or not text:
        return {"type": "unknown", "confidence": 0.0}
    p = m["clf"].predict_proba(m["vec"].transform([text]))[0]
    i = int(p.argmax())
    return {"type": m["clf"].classes_[i], "confidence": round(float(p[i]), 3)}


def refund(claim_type: str, price: float, days: int, damage_conf: float, severity: float | None = None) -> float | None:
    m = _load()
    if not m or claim_type not in TYPES:
        return None
    sev = damage_conf if severity is None else severity
    x = [price, days, damage_conf, sev] + [int(claim_type == t) for t in TYPES]
    return round(float(m["reg"].predict(np.array([x]))[0]), 2)


def cluster(text: str) -> int | None:
    m = _load()
    return int(m["km"].predict(m["vec"].transform([text]))[0]) if m and text else None


def cluster_terms(k: int = 5) -> dict[int, list[str]]:
    """Top TF-IDF terms per cluster centre: a readable label for each failure group."""
    m = _load()
    if not m:
        return {}
    vocab = np.array(m["vec"].get_feature_names_out())
    return {i: vocab[np.argsort(c)[::-1][:k]].tolist() for i, c in enumerate(m["km"].cluster_centers_)}
