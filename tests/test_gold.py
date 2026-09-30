"""Tests for the gold-set tooling. The annotators here are simulated; no labels are committed."""
import json

import pytest

from eval import label, run


@pytest.fixture
def gold(tmp_path, monkeypatch, png_b64):
    root = tmp_path / "verified"
    for name, val in {"ROOT": root, "CASES": root / "cases.jsonl", "ANN": root / "annotations.jsonl",
                      "ADJ": root / "adjudications.jsonl", "MEDIA": root / "media", "FROZEN": root / "verified.jsonl"}.items():
        monkeypatch.setattr(label, name, val)
    monkeypatch.setattr(run, "VERIFIED", root / "verified.jsonl")
    photo = tmp_path / "p.png"
    import base64
    photo.write_bytes(base64.b64decode(png_b64()))
    return root, photo


def annotate(monkeypatch, who, answers):
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _="": next(it))
    label.main(["annotate", "--annotator", who])


def test_full_flow_agreement_adjudication_and_eval(gold, monkeypatch):
    root, photo = gold
    label.main(["add", "--id", "G1", "--order", "ORD1", "--text", "cup arrived cracked", "--amount", "499",
                "--days", "2", "--source", "hand_authored_real_evidence", "--customer", "cu-1", "--photo", str(photo)])
    label.main(["add", "--id", "G2", "--order", "BAD2", "--text", "never got it", "--source", "real_customer", "--customer", "cu-2"])
    annotate(monkeypatch, "a", ["escalate", "photo unclear", "2", "reject", "no such order", "3"])
    annotate(monkeypatch, "b", ["escalate", "unclear", "2", "escalate", "maybe typo", "1"])
    ag = label.agreement()
    assert ag["double_annotated"] == 2 and ag["raw_agreement"] == 0.5 and ag["disagreements"][0]["id"] == "G2"

    label.main(["freeze"])
    assert [json.loads(l)["id"] for l in (root / "verified.jsonl").read_text().splitlines()] == ["G1"]  # G2 unresolved

    label.main(["adjudicate", "--id", "G2", "--label", "reject", "--note", "order id does not exist"])
    label.main(["freeze"])
    rows = [json.loads(l) for l in (root / "verified.jsonl").read_text().splitlines()]
    assert {r["id"]: r["label_method"] for r in rows} == {"G1": "agreed", "G2": "adjudicated"}
    assert all(r["split"] in {"dev", "test"} for r in rows)

    cases = run.load_cases("verified")
    assert cases[0]["claim"]["image_b64"] and cases[1]["expected"] == "reject"


def test_synthetic_cases_cannot_enter_the_gold_set(gold):
    with pytest.raises(SystemExit):
        label.main(["add", "--id", "S1", "--order", "ORD9", "--text", "x", "--source", "synthetic"])


def test_photos_are_stored_without_exif(gold, tmp_path):
    from PIL import Image
    src = tmp_path / "gps.jpg"
    im = Image.new("RGB", (64, 64), "red")
    exif = Image.Exif(); exif[0x010F] = "PhoneMaker"          # camera make
    im.save(src, exif=exif)
    label.main(["add", "--id", "E1", "--order", "ORD3", "--text", "x", "--source", "real_customer", "--photo", str(src)])
    stored = next((gold[0] / "media").glob("E1-photo.jpg"))
    assert len(Image.open(stored).getexif()) == 0


def test_kappa():
    assert label.kappa([("approve", "approve"), ("reject", "reject")]) == 1.0
    assert label.kappa([("approve", "reject"), ("reject", "approve")]) < 0
