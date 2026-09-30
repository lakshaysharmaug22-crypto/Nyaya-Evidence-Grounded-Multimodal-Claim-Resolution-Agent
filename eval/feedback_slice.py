"""Measure how much a gold set would contribute to the manual correction queue."""


def summarize(predictions: list[str], labels: list[str]) -> dict:
    if len(predictions) != len(labels):
        raise ValueError("predictions and labels must have equal length")
    disagreements = [(p, y) for p, y in zip(predictions, labels) if p != y and y in ("approve", "reject")]
    return {
        "n": len(labels),
        "disagreements": len(disagreements),
        "label_counts": {
            "approve": sum(y == "approve" for _, y in disagreements),
            "reject": sum(y == "reject" for _, y in disagreements),
        },
    }
