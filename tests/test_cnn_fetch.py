import hashlib

import pytest

from ml import infer


class _Resp:
    def __init__(self, data): self.data = data
    def read(self, n=-1): return self.data
    def __enter__(self): return self
    def __exit__(self, *a): return False


@pytest.fixture
def model_path(tmp_path, monkeypatch):
    p = tmp_path / "damage.int8.onnx"
    monkeypatch.setattr(infer, "MODEL", p)
    return p


def test_download_is_kept_only_when_checksum_matches(model_path, monkeypatch):
    blob = b"fake-model-bytes"
    monkeypatch.setattr(infer.urllib.request, "urlopen", lambda url, timeout: _Resp(blob))
    monkeypatch.setenv("CNN_MODEL_URL", "https://example.com/damage.int8.onnx")
    monkeypatch.setenv("CNN_MODEL_SHA256", hashlib.sha256(blob).hexdigest())
    assert infer.fetch_model() and model_path.read_bytes() == blob


def test_checksum_mismatch_leaves_no_file(model_path, monkeypatch):
    monkeypatch.setattr(infer.urllib.request, "urlopen", lambda url, timeout: _Resp(b"tampered"))
    monkeypatch.setenv("CNN_MODEL_URL", "https://example.com/damage.int8.onnx")
    monkeypatch.setenv("CNN_MODEL_SHA256", "0" * 64)
    assert not infer.fetch_model() and not model_path.exists()


def test_http_url_or_missing_checksum_is_refused(model_path, monkeypatch):
    monkeypatch.setattr(infer.urllib.request, "urlopen", lambda *a, **k: pytest.fail("must not download"))
    monkeypatch.setenv("CNN_MODEL_URL", "http://example.com/m.onnx")
    monkeypatch.setenv("CNN_MODEL_SHA256", "a" * 64)
    assert not infer.fetch_model()
    monkeypatch.setenv("CNN_MODEL_URL", "https://example.com/m.onnx")
    monkeypatch.delenv("CNN_MODEL_SHA256")
    assert not infer.fetch_model()
