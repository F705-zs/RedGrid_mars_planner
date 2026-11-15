"""Cost providers: AlgorithmCostProvider (weights table, local) and HttpModelCostProvider (trained model, HTTP)."""
from __future__ import annotations

import math

import numpy as np

from ..enums import GROUPS
from . import arrays
from .contracts import CostFactors, CostRequest, ProviderError, ProviderInfo
from .http_base import HttpProviderBase


class AlgorithmCostProvider:
    """logFactor(group, square) = sum over the square's categories in that group of ln(weight).

    Weights come from the ACTIVE CostModel; FIXED categories always use version 0 (Cost-Weight Model V1).
    Reference categories have weight 1 and add 0.
    """

    def __init__(self, cost_models, categories=None):
        self.cost_models = cost_models
        self._model = None
        self._categories = categories

    def _active(self):
        if self._model is None:
            self._model = self.cost_models.get_active()
        return self._model

    def info(self) -> ProviderInfo:
        return ProviderInfo("algorithm-weights", "ALGORITHM", "LOCAL", f"weights-v{self._active().version}")

    def is_ready(self) -> bool:
        return True

    def effective_weights(self) -> dict[str, float]:
        active = self._active()
        weights = {w.category_key: w.weight for w in active.weights}
        categories = self._categories or self.cost_models.get_categories()
        fixed = [c.key for c in categories if c.scope == "FIXED"]
        if fixed and active.version != 0:
            v0 = {w.category_key: w.weight for w in self.cost_models.get_by_version(0).weights}
            for k in fixed:
                weights[k] = v0[k]
        return weights

    def cost_factors(self, req: CostRequest) -> CostFactors:
        categories = self._categories or self.cost_models.get_categories()
        by_key = {c.key: c for c in categories}
        if [c.key for c in sorted(categories, key=lambda c: c.bit)] != req.category_keys:
            raise ProviderError("category catalog mismatch")
        weights = self.effective_weights()
        L = np.zeros((len(GROUPS), req.height, req.width), dtype=np.float32)
        for key, w in weights.items():
            if w == 1.0:
                continue
            c = by_key[key]
            mask = ((req.category_bits >> np.uint32(c.bit)) & np.uint32(1)).astype(bool)
            L[GROUPS.index(c.group)][mask] += math.log(w)
        hazard = [math.log(weights[c.key]) for c in categories if c.group == "HAZARD" and weights[c.key] > 1]
        floor = min(hazard) if hazard else 1e-9
        return CostFactors(provider=self.info(), log_factors=L, hazard_floor=floor, cost_model_id=self._active().id)


class HttpModelCostProvider(HttpProviderBase):
    def info(self) -> ProviderInfo:
        h = self._health or {}
        return ProviderInfo(h.get("name", "model-cost"), "MODEL", "HTTP", str(h.get("version", "unknown")),
                            "READY" if self._ready else "UNAVAILABLE")

    def cost_factors(self, req: CostRequest) -> CostFactors:
        body = {"requestId": req.request_id, "regionId": req.region_id, "window": req.window.as_dict(),
                "cellSizeM": req.cell_size_m, "width": req.width, "height": req.height,
                "categoryCatalogVersion": req.category_catalog_version, "categoryKeys": req.category_keys,
                "categoryBits": arrays.encode(req.category_bits, "uint32"), "routable": arrays.encode(req.routable, "uint8")}
        ans = self._post("/v1/cost-factors", body)
        p = ans.get("provider", {})
        info = ProviderInfo(p.get("name", "model-cost"), "MODEL", "HTTP", str(p.get("version", "unknown")))
        return CostFactors(provider=info, log_factors=arrays.decode(ans["logFactors"]).astype(np.float32),
                           hazard_floor=float(ans["hazardFloor"]), groups=list(ans.get("groups", [])))
