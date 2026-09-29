# ML

Colab or Kaggle GPU:

```
pip install torch torchvision scikit-learn onnx onnxruntime pillow numpy
python ml/train_cnn.py --data /path/to/data --epochs 8
```

Data is an ImageFolder split: `train/{damaged,intact}` and `val/{damaged,intact}`. Use a public product or vehicle damage dataset, plus intact product photos, and hold out a validation set the model never sees.

After training, copy `artifacts/damage.int8.onnx` back here. `infer.py` picks it up and the agent's photo node can call `damage_confidence`.

`ImageFolder` sorts classes alphabetically, so `damaged` is index 0 and `intact` is index 1. That matches the default in `infer.py`.

- `quality_gate.py` blur, brightness and size checks before upload
- `dedupe.py` perceptual-hash duplicate detection
- `infer.py` ONNX inference

## Tabular models

`python -m ml.train_tabular` trains a TF-IDF + logistic regression claim-type classifier, a gradient-boosting refund regressor and a KMeans clusterer on synthetic claims (`synth.py`), and writes `artifacts/tabular_metrics.json`. CI runs it before the eval. The metrics are from synthetic data, so replace `synth.py` with real or hand-verified claims before quoting numbers.
