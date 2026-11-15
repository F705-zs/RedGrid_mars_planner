"""ProviderChain: try providers in order; skip any not ready, too slow or invalid; the last one is local and always ready."""
from __future__ import annotations

import logging
from typing import Callable

from .contracts import ProviderResult

log = logging.getLogger(__name__)


class ProviderChain:
    def __init__(self, label: str, providers: list, validator: Callable | None = None):
        if not providers:
            raise ValueError(f"{label}: at least one provider is required")
        last = providers[-1].info()
        if last.transport != "LOCAL":
            raise ValueError(f"{label}: the last provider must be local and always ready (found {last.name})")
        self.label = label
        self.providers = providers
        self.validator = validator

    def call(self, method: str, *args, validate_args: tuple = ()) -> ProviderResult:
        skipped: list[str] = []
        for p in self.providers:
            info = p.info()
            if not p.is_ready():
                skipped.append(f"{info.name} ({info.kind.lower()}) not ready")
                continue
            try:
                value = getattr(p, method)(*args)
                if self.validator:
                    self.validator(value, *validate_args)
                return ProviderResult(value=value, answered_by=value.provider if hasattr(value, "provider") else info, skipped=skipped)
            except Exception as exc:  # timeout, HTTP error, invalid answer
                log.warning("%s: provider %s failed: %s", self.label, info.name, exc)
                skipped.append(f"{info.name} ({info.kind.lower()}) failed: {str(exc)[:120]}")
        raise RuntimeError(f"{self.label}: no provider answered ({'; '.join(skipped)})")

    def statuses(self) -> list[dict]:
        out = []
        for p in self.providers:
            info = p.info()
            info.status = "READY" if p.is_ready() else "UNAVAILABLE"
            out.append(info.as_dict())
        return out
