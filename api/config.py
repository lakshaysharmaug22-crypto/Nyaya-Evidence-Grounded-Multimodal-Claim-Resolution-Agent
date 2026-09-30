"""Settings read once from the environment and validated at startup.

`NYAYA_ENV=production` turns unsafe defaults into startup errors instead of silent risks.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, lo: int, hi: int) -> int:
    raw = os.getenv(name)
    try:
        v = int(raw) if raw is not None else default
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if not lo <= v <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}, got {v}")
    return v


@dataclass(frozen=True)
class Settings:
    env: str = "development"
    data_dir: Path = Path("data")
    agent_token: str | None = None
    origins: list[str] = field(default_factory=lambda: ["*"])
    rate_per_min: int = 30
    max_body_mb: int = 12
    allow_score_overrides: bool = True
    log_json: bool = False

    @property
    def production(self) -> bool:
        return self.env == "production"


def load() -> Settings:
    env = os.getenv("NYAYA_ENV", "development").strip().lower()
    token = os.getenv("AGENT_TOKEN") or None
    origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()] or ["*"]
    s = Settings(
        env=env,
        data_dir=Path(os.getenv("DATA_DIR", "data")),
        agent_token=token,
        origins=origins,
        rate_per_min=_int("RATE_LIMIT_PER_MIN", 30, 1, 10_000_000),
        max_body_mb=_int("MAX_BODY_MB", 12, 1, 100),
        # Score fields (damage_conf, modalities_agree, ...) in a claim body are a demo/eval shortcut.
        # Open in development; in production only if explicitly enabled.
        allow_score_overrides=_bool("ALLOW_SCORE_OVERRIDES", env != "production"),
        log_json=_bool("LOG_JSON", env == "production"),
    )
    if s.production:
        problems = []
        if not token or len(token) < 16:
            problems.append("AGENT_TOKEN must be set to at least 16 characters")
        if "*" in origins:
            problems.append("ALLOWED_ORIGINS must list the frontend origin(s), not *")
        if problems:
            raise RuntimeError("Refusing to start in production: " + "; ".join(problems))
    return s
