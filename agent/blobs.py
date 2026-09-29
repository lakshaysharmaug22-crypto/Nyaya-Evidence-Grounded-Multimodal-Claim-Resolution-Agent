"""Large uploads (photos, invoices) live on disk, not in graph state, so checkpoints stay small."""
import base64
import os
from pathlib import Path


def _dir() -> Path:
    d = Path(os.getenv("DATA_DIR", "data")) / "blobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def put(claim_id: str, kind: str, b64: str) -> str:
    safe = "".join(ch for ch in claim_id if ch.isalnum() or ch in "-_")[:80] or "anon"
    path = _dir() / f"{safe}.{kind}"
    path.write_bytes(base64.b64decode(b64))
    return str(path)


def get_b64(claim: dict, kind: str) -> str | None:
    """kind: 'image' or 'invoice'. Accepts an inline base64 field or a stored reference."""
    inline = claim.get(f"{'image' if kind == 'image' else 'invoice'}_b64")
    if inline:
        return inline
    ref = claim.get(f"{kind}_ref")
    if ref and Path(ref).is_file() and Path(ref).resolve().is_relative_to(_dir().resolve()):
        return base64.b64encode(Path(ref).read_bytes()).decode()
    return None
