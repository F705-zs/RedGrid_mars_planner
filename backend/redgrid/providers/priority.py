"""Priority resolvers (weighted product model).

Square cost = base x prod_g factor_g ** s_g. The exponent s_g of a group is the relative importance of its slider:
s_g = w_g / mean(w) = 7 w_g for seven normalised weights, so equal priorities give s_g = 1 and leave the weights
exactly as provided. The weighted product model is dimension-free and keeps a neutral factor (1) neutral
(Triantaphyllou 2000, Multi-criteria Decision Making Methods: A Comparative Study, ch. 2).
Distance and resource use are the two base-cost objectives, combined by simple additive weighting after each is
normalised to 1 on flat regolith: d = w_distance / (w_distance + w_return).
"""
from __future__ import annotations

from .contracts import GroupScales, PriorityRequest, ProviderInfo
from .http_base import HttpProviderBase

N_SLIDERS = 7


class AlgorithmPriorityResolver:
    VERSION = "wpm-1"

    def info(self) -> ProviderInfo:
        return ProviderInfo("algorithm-priorities", "ALGORITHM", "LOCAL", self.VERSION)

    def is_ready(self) -> bool:
        return True

    def resolve(self, req: PriorityRequest) -> GroupScales:
        w = req.priorities
        k = float(N_SLIDERS)
        dist, ret = w["distanceWeight"], w["returnWeight"]
        d = dist / (dist + ret) if (dist + ret) > 0 else 0.5
        return GroupScales(provider=self.info(), hazard=k * w["safetyWeight"], terrain=k * w["walkingDifficultyWeight"],
                           science=k * w["scienceWeight"], communication=k * w["environmentWeight"],
                           uncertainty=max(1.0, k * w["environmentWeight"]), rover_path=k * w["roverPathWeight"],
                           distance_weight=d)


class HttpModelPriorityResolver(HttpProviderBase):
    def info(self) -> ProviderInfo:
        h = self._health or {}
        return ProviderInfo(h.get("name", "model-priorities"), "MODEL", "HTTP", str(h.get("version", "unknown")),
                            "READY" if self._ready else "UNAVAILABLE")

    def resolve(self, req: PriorityRequest) -> GroupScales:
        a = self._post("/v1/priority-scales", {"profile": req.profile, "priorities": req.priorities, "mix": req.mix})
        p = a.get("provider", {})
        info = ProviderInfo(p.get("name", "model-priorities"), "MODEL", "HTTP", str(p.get("version", "unknown")))
        return GroupScales(provider=info, hazard=float(a["hazard"]), terrain=float(a["terrain"]), science=float(a["science"]),
                           communication=float(a["communication"]), uncertainty=float(a["uncertainty"]),
                           rover_path=float(a["roverPath"]), distance_weight=float(a["distanceWeight"]))
