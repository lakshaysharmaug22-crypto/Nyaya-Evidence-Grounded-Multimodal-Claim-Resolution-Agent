# ML

## Damage CNN

The training pipeline is complete and checked end to end with `python -m ml.train_cnn --smoke` (one quick CPU run on generated shapes, written to `artifacts/smoke/`, which inference ignores). Production weights come from a GPU run on a public dataset. Until they are deployed, `damage_confidence` returns 0.0 and photo claims go to human review rather than auto-approval.

Train on Kaggle (free GPU): open `notebooks/train_damage_kaggle.ipynb`, attach a public damaged/intact photo dataset (e.g. *Damaged and Intact Packages*), set its licence, run all. Or anywhere with a GPU:

```
pip install torch torchvision onnx onnxruntime onnxscript
python -m ml.train_cnn --data /path/to/dataset --epochs 8 \
  --dataset-name "..." --dataset-url "..." --license "..."
```

What the script does:
- Finds the classes from folder names (`intact`/`undamaged`/`good` vs `damaged`/`broken`/`defect`) and drops exact-duplicate images so none leak across splits.
- Uses the dataset's own train/val/test folders if it has them; otherwise it makes a seeded, stratified 70/15/15 split and saves it to `split.json`.
- Fine-tunes ImageNet EfficientNet-B0: head only for 2 epochs, then the full network at lr/10. It keeps the best epoch by validation F1.
- Reports accuracy, precision, recall, F1, ROC-AUC and the confusion matrix on the **held-out test split**, which is never used for training or model selection.
- Exports ONNX, quantizes to INT8 and checks that the INT8 model agrees with PyTorch on the test set.
- Writes `metrics.json` and `MODEL_CARD.md`: dataset and licence, counts, config, hardware, metrics, limitations.

Deploying the model without committing it: upload `damage.int8.onnx` as a GitHub release asset, then set `CNN_MODEL_URL` (the asset URL) and `CNN_MODEL_SHA256` (from `sha256sum`) on the API. It downloads the model on first use and refuses a file whose checksum does not match. Commit `MODEL_CARD.md` and `metrics.json` (they are not ignored) so the numbers in the README are traceable.

Inference (`infer.py`) uses the same preprocessing as validation: short side to 256, centre crop 224, ImageNet normalisation. Class index 0 is `damaged`.

- `quality_gate.py` blur, brightness and size checks before upload
- `dedupe.py` perceptual-hash duplicate detection
- `infer.py` ONNX inference

## Tabular models

`python -m ml.train_tabular` trains a TF-IDF + logistic regression claim-type classifier, a gradient-boosting refund regressor and a KMeans clusterer on synthetic claims (`synth.py`), and writes `artifacts/tabular_metrics.json`. CI runs it before the eval. The metrics are from synthetic data, so replace `synth.py` with real or hand-verified claims before quoting numbers.
