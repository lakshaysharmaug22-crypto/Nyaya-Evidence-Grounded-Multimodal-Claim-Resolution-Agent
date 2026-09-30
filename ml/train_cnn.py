"""Fine-tune EfficientNet-B0 for damaged / intact product photos and export an INT8 ONNX model.

Usage (Kaggle/Colab GPU, see ml/README.md and ml/notebooks/train_damage_kaggle.ipynb):
    python -m ml.train_cnn --data /kaggle/input/<dataset> --epochs 8 \
        --dataset-name "Damaged and Intact Packages" --dataset-url <url> --license "<license>"

Data: any folder tree where class folders are recognisable by name. Folders whose name contains
"intact", "undamaged", "good" or "ok" are the intact class; folders containing "damag", "broken",
"defect" or "crush" are the damaged class. If the tree already has train/ val/ test/ splits they are
used as-is; otherwise a seeded, stratified 70/15/15 split is made and written to split.json so the
exact test set can be re-created.

Outputs (ml/artifacts/): damage.pt, damage.onnx, damage.int8.onnx, metrics.json, split.json, MODEL_CARD.md
`--smoke` trains for one epoch on generated shapes, writes to ml/artifacts/smoke/ (never loaded by
infer.py) and exists only to prove the pipeline runs end to end. Its numbers mean nothing.
"""
import argparse
import hashlib
import json
import platform
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageDraw
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

ROOT_OUT = Path(__file__).parent / "artifacts"
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
CLASSES = ["damaged", "intact"]                  # index 0 = damaged, matches ml/infer.py
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
INTACT_KEYS = ("undamag", "intact", "good", "ok", "normal")
DAMAGED_KEYS = ("damag", "broken", "defect", "crush", "dent")
SPLITS = ("train", "val", "test")


def class_of(path: Path, root: Path) -> str | None:
    for part in reversed(path.relative_to(root).parts[:-1]):
        p = part.lower()
        if any(k in p for k in INTACT_KEYS):
            return "intact"
        if any(k in p for k in DAMAGED_KEYS):
            return "damaged"
    return None


def split_of(path: Path, root: Path) -> str | None:
    parts = [p.lower() for p in path.relative_to(root).parts[:-1]]
    for s, names in (("train", {"train", "training"}), ("val", {"val", "valid", "validation"}), ("test", {"test", "testing"})):
        if names & set(parts):
            return s
    return None


def sha1(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest()[:16]


def discover(root: Path, seed: int) -> dict[str, list[tuple[str, int]]]:
    files = [p for p in root.rglob("*") if p.suffix.lower() in IMG_EXT]
    labelled = [(p, class_of(p, root)) for p in files]
    labelled = [(p, c) for p, c in labelled if c]
    if not labelled:
        raise SystemExit(f"no images under {root} in folders named like {INTACT_KEYS} / {DAMAGED_KEYS}")
    # exact duplicates across the tree would leak between splits: keep the first copy only
    seen, uniq = set(), []
    for p, c in sorted(labelled):
        h = sha1(p)
        if h not in seen:
            seen.add(h); uniq.append((p, c))
    given = {split_of(p, root) for p, _ in uniq}
    out = {s: [] for s in SPLITS}
    if {"train", "val"} <= given:
        for p, c in uniq:
            out[split_of(p, root) or "train"].append((str(p), CLASSES.index(c)))
        if not out["test"]:                      # carve a test set out of val so it stays unseen
            rng = random.Random(seed); rng.shuffle(out["val"])
            half = len(out["val"]) // 2
            out["test"], out["val"] = out["val"][:half], out["val"][half:]
        return out
    rng = random.Random(seed)
    for c in CLASSES:
        items = [(str(p), CLASSES.index(c)) for p, k in uniq if k == c]
        rng.shuffle(items)
        n = len(items); a, b = int(n * 0.70), int(n * 0.85)
        out["train"] += items[:a]; out["val"] += items[a:b]; out["test"] += items[b:]
    return out


class Files(Dataset):
    def __init__(self, items, tf):
        self.items, self.tf = items, tf

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        path, y = self.items[i]
        return self.tf(Image.open(path).convert("RGB")), y


def make_smoke_data(root: Path, n: int = 48):
    """Procedural stand-ins: plain boxes vs boxes with jagged cracks. Only for testing the pipeline."""
    rng = random.Random(0)
    for c in CLASSES:
        (root / c).mkdir(parents=True, exist_ok=True)
        for i in range(n):
            im = Image.new("RGB", (160, 160), tuple(rng.randint(150, 230) for _ in range(3)))
            d = ImageDraw.Draw(im)
            d.rectangle([30, 30, 130, 130], fill=(170, 130, 80), outline=(90, 60, 30), width=3)
            if c == "damaged":
                pts = [(rng.randint(30, 130), rng.randint(30, 130)) for _ in range(6)]
                d.line(pts, fill=(20, 20, 20), width=4)
            im.save(root / c / f"{i}.png")


def evaluate(model, dl, dev):
    model.eval(); y, pred, prob = [], [], []
    with torch.no_grad():
        for x, t in dl:
            z = model(x.to(dev)).softmax(1).cpu()
            prob += z[:, 0].tolist(); pred += z.argmax(1).tolist(); y += t.tolist()
    yd = [1 if v == 0 else 0 for v in y]          # damaged is the positive class
    pd = [1 if v == 0 else 0 for v in pred]
    m = {"n": len(y), "accuracy": float(np.mean(np.array(y) == np.array(pred))),
         "f1": f1_score(yd, pd, zero_division=0), "precision": precision_score(yd, pd, zero_division=0),
         "recall": recall_score(yd, pd, zero_division=0),
         "confusion_matrix": {"labels": CLASSES, "rows_true_cols_pred": confusion_matrix(y, pred, labels=[0, 1]).tolist()}}
    if len(set(yd)) == 2:
        m["roc_auc"] = roc_auc_score(yd, prob)
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()}


def onnx_parity(model, onnx_path: Path, dl) -> dict:
    """Share of test images where the INT8 ONNX model predicts the same class as the PyTorch model."""
    import onnxruntime as ort
    s = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    same = total = 0; max_dp = 0.0
    model.eval()
    with torch.no_grad():
        for x, _ in dl:
            a = model(x).softmax(1).numpy()
            z = s.run(None, {"x": x.numpy()})[0]
            b = np.exp(z - z.max(1, keepdims=True)); b /= b.sum(1, keepdims=True)
            same += int((a.argmax(1) == b.argmax(1)).sum()); total += len(a)
            max_dp = max(max_dp, float(np.abs(a[:, 0] - b[:, 0]).max()))
    return {"agreement": round(same / max(total, 1), 4), "max_prob_diff": round(max_dp, 4), "n": total}


def model_card(out: Path, meta: dict):
    t, cm = meta["test"], meta["test"]["confusion_matrix"]["rows_true_cols_pred"]
    lines = [
        "# Damage classifier model card", "",
        "**This is a smoke run on generated shapes. The numbers are meaningless.**" if meta["smoke"] else "",
        f"- Model: EfficientNet-B0 ({'ImageNet-pretrained' if meta['pretrained'] else 'random init'}), 2-class head",
        f"- Dataset: {meta['dataset']['name']} ({meta['dataset']['url']}), license: {meta['dataset']['license']}",
        f"- Images after exact-duplicate removal: train {meta['counts']['train']}, val {meta['counts']['val']}, test {meta['counts']['test']}"
        f" (split seed {meta['config']['seed']}, manifest in split.json)",
        f"- Training: {meta['config']['epochs']} epochs, batch {meta['config']['bs']}, AdamW lr {meta['config']['lr']} "
        "(head only for 2 epochs, then full network at lr/10), label smoothing 0.05, "
        "augmentation RandomResizedCrop(224, 0.7-1.0), flip, colour jitter",
        f"- Best epoch by validation F1: {meta['best_epoch']} (val F1 {meta['best_val_f1']})",
        f"- Hardware: {meta['device']}, {meta['train_seconds']} s total", "",
        "## Held-out test set (never used for training or model selection)", "",
        "| Metric | Value |", "| --- | ---: |",
        *[f"| {k} | {t[k]} |" for k in ("n", "accuracy", "precision", "recall", "f1", "roc_auc") if k in t], "",
        "Confusion matrix (rows = true, cols = predicted; order damaged, intact):", "",
        f"`{cm}`", "",
        f"INT8 ONNX vs PyTorch on the test set: {meta['onnx_parity']['agreement']:.1%} same class, "
        f"max damaged-probability difference {meta['onnx_parity']['max_prob_diff']}.", "",
        "## Limitations", "",
        "- Trained on one public dataset; photos from real customers (lighting, phones, product types) will differ.",
        "- Binary damaged/intact only: no damage type, severity or location.",
        "- The test set comes from the same source as training data, so it measures in-distribution accuracy only.",
        "- The agent treats this score as one piece of evidence; policy rules, not the CNN, decide refunds.",
    ]
    (out / "MODEL_CARD.md").write_text("\n".join(l for l in lines if l is not None) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--weights", help="local EfficientNet-B0 state_dict (offline); default downloads ImageNet weights")
    ap.add_argument("--no-pretrained", action="store_true")
    ap.add_argument("--dataset-name", default="unspecified")
    ap.add_argument("--dataset-url", default="unspecified")
    ap.add_argument("--license", default="unspecified")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()

    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    out = ROOT_OUT / "smoke" if a.smoke else ROOT_OUT
    out.mkdir(parents=True, exist_ok=True)
    if a.smoke:
        data = out / "data"; make_smoke_data(data)
        a.epochs, a.no_pretrained, a.dataset_name = 3, True, "generated shapes (smoke test)"
    else:
        if not a.data:
            raise SystemExit("--data is required (or use --smoke)")
        data = Path(a.data)
    split = discover(data, a.seed)
    (out / "split.json").write_text(json.dumps({s: [[str(Path(p).relative_to(data)), CLASSES[y]] for p, y in v]
                                                for s, v in split.items()}, indent=0))
    counts = {s: len(v) for s, v in split.items()}
    print("images:", counts)

    tr = transforms.Compose([transforms.RandomResizedCrop(224, scale=(0.7, 1.0)), transforms.RandomHorizontalFlip(),
                             transforms.ColorJitter(0.3, 0.3, 0.2), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    ev = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224),   # same crop as ml/infer.py
                             transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    dl = {s: DataLoader(Files(split[s], tr if s == "train" else ev), a.bs, shuffle=s == "train", num_workers=a.workers)
          for s in SPLITS}

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if a.weights:
        model = models.efficientnet_b0(); model.load_state_dict(torch.load(a.weights, map_location="cpu"), strict=False)
    else:
        model = models.efficientnet_b0(weights=None if a.no_pretrained else models.EfficientNet_B0_Weights.DEFAULT)
    pretrained = bool(a.weights) or not a.no_pretrained
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, 2)
    model.to(dev)

    for p in model.features.parameters():          # stage 1: head only
        p.requires_grad = False
    opt = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=a.lr)
    lossf, best, best_ep, t_start = nn.CrossEntropyLoss(label_smoothing=0.05), -1.0, -1, time.time()
    for ep in range(a.epochs):
        if ep == 2:                                # stage 2: unfreeze, lower lr
            for p in model.features.parameters():
                p.requires_grad = True
            opt = torch.optim.AdamW(model.parameters(), lr=a.lr / 10)
        model.train(); t0 = time.time()
        for x, y in dl["train"]:
            opt.zero_grad(); lossf(model(x.to(dev)), y.to(dev)).backward(); opt.step()
        m = evaluate(model, dl["val"], dev)
        print(f"epoch {ep} val f1={m['f1']:.3f} p={m['precision']:.3f} r={m['recall']:.3f} ({time.time()-t0:.0f}s)")
        if m["f1"] > best:
            best, best_ep = m["f1"], ep
            torch.save(model.state_dict(), out / "damage.pt")

    model.load_state_dict(torch.load(out / "damage.pt", map_location="cpu")); model.eval().cpu()
    test = evaluate(model, dl["test"], "cpu")
    torch.onnx.export(model, torch.randn(1, 3, 224, 224), out / "damage.onnx", input_names=["x"],
                      output_names=["logits"], dynamic_axes={"x": {0: "b"}}, opset_version=17, dynamo=False)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    quantize_dynamic(str(out / "damage.onnx"), str(out / "damage.int8.onnx"), weight_type=QuantType.QUInt8)
    meta = {"smoke": a.smoke, "pretrained": pretrained, "classes": CLASSES, "counts": counts,
            "dataset": {"name": a.dataset_name, "url": a.dataset_url, "license": a.license},
            "config": {"epochs": a.epochs, "bs": a.bs, "lr": a.lr, "seed": a.seed},
            "best_epoch": best_ep, "best_val_f1": best, "test": test,
            "onnx_parity": onnx_parity(model, out / "damage.int8.onnx", dl["test"]),
            "device": f"{dev} ({platform.processor() or platform.machine()})",
            "train_seconds": round(time.time() - t_start), "torch": torch.__version__}
    (out / "metrics.json").write_text(json.dumps(meta, indent=2))
    model_card(out, meta)
    print(json.dumps({"test": test, "onnx_parity": meta["onnx_parity"]}, indent=2), "\n->", out)


if __name__ == "__main__":
    main()
