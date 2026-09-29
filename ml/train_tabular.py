"""Train claim-type classifier, refund regressor, and failure clusterer. Writes ml/artifacts/tabular.joblib + tabular_metrics.json."""
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.cluster import KMeans
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, mean_absolute_error
from sklearn.model_selection import train_test_split

from .synth import TYPES, make

OUT = Path(__file__).parent / "artifacts"


def feats(rows, type_idx):
    return np.array([[r["price"], r["days"], r["damage_conf"], r["severity"]] + [int(type_idx[i] == k) for k in range(len(TYPES))]
                     for i, r in enumerate(rows)], dtype=float)


def main(n: int = 6000):
    OUT.mkdir(exist_ok=True)
    rows = make(n)
    tr, te = train_test_split(rows, test_size=.25, random_state=3)

    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
    clf = LogisticRegression(max_iter=1000).fit(vec.fit_transform([r["text"] for r in tr]), [r["type"] for r in tr])
    pred = clf.predict(vec.transform([r["text"] for r in te]))
    f1 = f1_score([r["type"] for r in te], pred, average="macro")

    idx = lambda rs: [TYPES.index(r["type"]) for r in rs]
    reg = GradientBoostingRegressor(random_state=3).fit(feats(tr, idx(tr)), [r["refund"] for r in tr])
    mae = mean_absolute_error([r["refund"] for r in te], reg.predict(feats(te, idx(te))))
    base_mae = mean_absolute_error([r["refund"] for r in te], [np.mean([r["refund"] for r in tr])] * len(te))

    X = vec.transform([r["text"] for r in tr])
    km = KMeans(n_clusters=5, n_init=10, random_state=3).fit(X)

    joblib.dump({"vec": vec, "clf": clf, "reg": reg, "km": km}, OUT / "tabular.joblib")
    m = {"claim_type_macro_f1": round(f1, 4), "refund_mae_inr": round(mae, 2), "refund_baseline_mae_inr": round(base_mae, 2),
         "n_train": len(tr), "n_test": len(te), "data": "synthetic"}
    (OUT / "tabular_metrics.json").write_text(json.dumps(m, indent=2))
    print(json.dumps(m, indent=2))


if __name__ == "__main__":
    main()
