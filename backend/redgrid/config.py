"""Configuration. Every value can be overridden with an environment variable of the same name prefixed REDGRID_."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(f"REDGRID_{name}", default)


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in _env(name, default).split(",") if x.strip()]


class Config:
    DATABASE = _env("DATABASE", str(BASE_DIR / "instance" / "redgrid.sqlite3"))
    DATA_DIR = _env("DATA_DIR", str(BASE_DIR / "data"))
    CORS_ORIGINS = _list("CORS_ORIGINS", "http://localhost:8080,http://localhost:5173,http://localhost:3000")

    # Provider chains (tried in order; the last one must be local and always ready)
    COST_PROVIDERS = _list("COST_PROVIDERS", "algorithm")
    PRIORITY_RESOLVERS = _list("PRIORITY_RESOLVERS", "algorithm")
    RESOURCE_PROVIDERS = _list("RESOURCE_PROVIDERS", "sensor,defaults")
    MODEL_COST_URL = _env("MODEL_COST_URL", "")
    MODEL_PRIORITY_URL = _env("MODEL_PRIORITY_URL", "")
    SENSOR_URL = _env("SENSOR_URL", "")

    HEALTH_TIMEOUT_S = 5.0          # RedGrid API Contract, Appendix A
    HEALTH_CACHE_S = 30.0           # RedGrid Class Specification, ProviderChain
    JSON_SORT_KEYS = False
    REGION_ID = 1                   # the prototype has one region


class TestConfig(Config):
    TESTING = True
