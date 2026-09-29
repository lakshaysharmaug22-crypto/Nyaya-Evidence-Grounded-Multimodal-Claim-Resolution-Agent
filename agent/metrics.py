"""Per-node metrics: latency, tokens, cost, outcome."""
import time
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class RunMetrics:
    nodes: dict = field(default_factory=dict)
    tokens: int = 0
    cost_inr: float = 0.0

    @contextmanager
    def node(self, name: str):
        t = time.perf_counter()
        try:
            yield
        finally:
            self.nodes[name] = round((time.perf_counter() - t) * 1000, 2)

    def add_llm(self, tokens: int, rate_per_1k_inr: float = 0.2):
        self.tokens += tokens
        self.cost_inr += tokens / 1000 * rate_per_1k_inr

    @property
    def total_ms(self) -> float:
        return round(sum(self.nodes.values()), 2)
