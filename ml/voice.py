"""Voice note -> text with faster-whisper (multilingual, handles Hindi and English).

Not exercised in the sandbox build (needs the model download). Install with:
    pip install faster-whisper
The model loads lazily on first use. Set WHISPER_MODEL (default 'small'; use 'base' on small machines).
"""
import base64
import io
import os

_model = None


def _load():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(os.getenv("WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
    return _model


def transcribe(audio_b64: str) -> dict:
    try:
        audio = base64.b64decode(audio_b64, validate=True)
        if not audio:
            raise ValueError("empty audio")
        segments, info = _load().transcribe(io.BytesIO(audio), vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        return {"ok": bool(text), "text": text, "language": info.language}
    except Exception as e:
        return {"ok": False, "text": "", "error": f"{type(e).__name__}: {e}"}
