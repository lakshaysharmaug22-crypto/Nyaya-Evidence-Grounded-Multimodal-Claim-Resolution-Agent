"""Perceptual-hash duplicate detection (average hash + Hamming distance). No model call."""
import numpy as np
from PIL import Image


def ahash(img: Image.Image, size: int = 16) -> int:
    a = np.asarray(img.convert("L").resize((size, size), Image.LANCZOS), dtype=np.float32)
    bits = (a > a.mean()).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


class DupIndex:
    def __init__(self, threshold: int = 12):
        self.threshold, self.items = threshold, []

    def check_and_add(self, claim_id: str, img: Image.Image) -> dict:
        h = ahash(img)
        for cid, other in self.items:
            if cid != claim_id and hamming(h, other) <= self.threshold:
                return {"duplicate": True, "matches": cid}
        self.items.append((claim_id, h))
        return {"duplicate": False, "matches": None}
