"""Reference remote provider (RedGrid API Contract, Appendix A) for the model team and for tests.

It answers the cost and priority contracts over HTTP. Its "model" is a weights table you pass in (default: the
hand-set version 0 weights), so its answers equal the local algorithm's. Replace cost_factors() with a real model.

Run:  python -m tools.mock_model_provider --port 5055
Then: REDGRID_COST_PROVIDERS=model,algorithm  REDGRID_MODEL_COST_URL=http://localhost:5055
"""
from __future__ import annotations

import argparse
import math

import numpy as np
from flask import Flask, jsonify, request

from redgrid.providers import arrays

GROUPS = ["HAZARD", "TERRAIN", "SCIENCE", "COMMUNICATION", "UNCERTAINTY", "ROVER_PATH"]
V0 = {  # category key -> (group, weight); version 0 placeholders (slope and terrain class = 1: physics is in the base cost)
    "rough_medium": ("TERRAIN", 1.3), "rough_high": ("TERRAIN", 2.0), "near_rim_scarp": ("HAZARD", 2.0),
    "hazard_0_50": ("HAZARD", 4.0), "hazard_50_200": ("HAZARD", 1.5), "near_science": ("SCIENCE", 0.6),
    "near_rover_path": ("ROVER_PATH", 0.9), "no_comm": ("COMMUNICATION", 1.5), "data_missing": ("UNCERTAINTY", 5.0),
}


def create_app(weights: dict | None = None, name: str = "mock-model", version: str = "0.1") -> Flask:
    weights = weights or V0
    app = Flask(__name__)

    @app.get("/v1/health")
    def health():
        return jsonify({"status": "READY", "name": name, "version": version, "kind": "MODEL"})

    @app.post("/v1/cost-factors")
    def cost_factors():
        req = request.get_json()
        bits = arrays.decode(req["categoryBits"])
        keys = req["categoryKeys"]
        L = np.zeros((len(GROUPS), req["height"], req["width"]), np.float32)
        for b, key in enumerate(keys):
            if key in weights:
                g, w = weights[key]
                L[GROUPS.index(g)][((bits >> np.uint32(b)) & np.uint32(1)).astype(bool)] += math.log(w)
        floor = min(math.log(w) for g, w in weights.values() if g == "HAZARD" and w > 1)
        return jsonify({"provider": {"name": name, "kind": "MODEL", "transport": "HTTP", "version": version},
                        "groups": GROUPS, "logFactors": arrays.encode(L, "float16"), "hazardFloor": floor})

    @app.post("/v1/priority-scales")
    def priority_scales():
        p = request.get_json()["priorities"]
        d, r = p["distanceWeight"], p["returnWeight"]
        return jsonify({"provider": {"name": name, "kind": "MODEL", "transport": "HTTP", "version": version},
                        "hazard": 7 * p["safetyWeight"], "terrain": 7 * p["walkingDifficultyWeight"], "science": 7 * p["scienceWeight"],
                        "communication": 7 * p["environmentWeight"], "uncertainty": max(1.0, 7 * p["environmentWeight"]),
                        "roverPath": 7 * p["roverPathWeight"], "distanceWeight": d / (d + r) if d + r > 0 else 0.5})

    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5055)
    create_app().run(port=ap.parse_args().port)
