"""Fine-tune a small CNN for damage / no-damage on product photos.

Colab/Kaggle usage:
    !pip install torch torchvision scikit-learn onnx onnxruntime
    !python ml/train_cnn.py --data /content/data --epochs 8

Data layout (ImageFolder):
    data/train/damaged/*.jpg   data/train/intact/*.jpg
    data/val/damaged/*.jpg     data/val/intact/*.jpg

Outputs: ml/artifacts/damage.pt, damage.onnx, damage.int8.onnx, metrics.json
"""
import argparse
import json
import time
from pathlib import Path

import torch
import torch.nn as nn
from sklearn.metrics import f1_score, precision_score, recall_score
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms

OUT = Path(__file__).parent / "artifacts"
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


def loaders(root: Path, bs: int):
    tr = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.7, 1.0)), transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.3, 0.3, 0.2), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    va = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224),
                             transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    dtr, dva = datasets.ImageFolder(root / "train", tr), datasets.ImageFolder(root / "val", va)
    return (DataLoader(dtr, bs, shuffle=True, num_workers=2), DataLoader(dva, bs, num_workers=2), dtr.classes)


def evaluate(model, dl, dev, pos):
    model.eval(); y, p = [], []
    with torch.no_grad():
        for x, t in dl:
            p += model(x.to(dev)).argmax(1).cpu().tolist(); y += t.tolist()
    return {"f1": f1_score(y, p, pos_label=pos), "precision": precision_score(y, p, pos_label=pos),
            "recall": recall_score(y, p, pos_label=pos), "n": len(y)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    a = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    dtr, dva, classes = loaders(Path(a.data), a.bs)
    pos = classes.index("damaged")
    model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(classes))
    model.to(dev)

    for p in model.features.parameters():          # stage 1: head only
        p.requires_grad = False
    opt = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=a.lr)
    lossf, best = nn.CrossEntropyLoss(label_smoothing=0.05), 0.0
    OUT.mkdir(exist_ok=True)
    for ep in range(a.epochs):
        if ep == 2:                                # stage 2: unfreeze, lower lr
            for p in model.features.parameters():
                p.requires_grad = True
            opt = torch.optim.AdamW(model.parameters(), lr=a.lr / 10)
        model.train(); t0 = time.time()
        for x, y in dtr:
            opt.zero_grad(); lossf(model(x.to(dev)), y.to(dev)).backward(); opt.step()
        m = evaluate(model, dva, dev, pos)
        print(f"epoch {ep} f1={m['f1']:.3f} p={m['precision']:.3f} r={m['recall']:.3f} ({time.time()-t0:.0f}s)")
        if m["f1"] >= best:
            best = m["f1"]; torch.save(model.state_dict(), OUT / "damage.pt")
            (OUT / "metrics.json").write_text(json.dumps({**m, "classes": classes}, indent=2))

    model.load_state_dict(torch.load(OUT / "damage.pt")); model.eval().cpu()
    dummy = torch.randn(1, 3, 224, 224)
    torch.onnx.export(model, dummy, OUT / "damage.onnx", input_names=["x"], output_names=["logits"],
                      dynamic_axes={"x": {0: "b"}}, opset_version=17)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    quantize_dynamic(str(OUT / "damage.onnx"), str(OUT / "damage.int8.onnx"), weight_type=QuantType.QUInt8)
    print("best f1", best, "->", OUT)


if __name__ == "__main__":
    main()
