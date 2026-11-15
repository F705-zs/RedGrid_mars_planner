import threading

import numpy as np
import pytest
from werkzeug.serving import make_server

from redgrid.providers import arrays
from redgrid.providers.chain import ProviderChain
from redgrid.providers.contracts import CostFactors, ProviderInfo, validate_cost_factors
from redgrid.providers.cost import HttpModelCostProvider
from redgrid.providers.priority import AlgorithmPriorityResolver


def test_array_roundtrip():
    for a in (np.arange(12, dtype=np.uint32).reshape(3, 4), np.random.rand(6, 5, 4).astype(np.float32)):
        b = arrays.decode(arrays.encode(a))
        assert b.shape == a.shape and np.allclose(a, b)


def test_last_provider_must_be_local():
    with pytest.raises(ValueError):
        ProviderChain("x", [HttpModelCostProvider("http://127.0.0.1:9", 1)])


def test_unreachable_model_falls_back_to_algorithm():
    chain = ProviderChain("PriorityResolver", [HttpModelCostProvider("http://127.0.0.1:9", 1, health_timeout_s=0.5),
                                               AlgorithmPriorityResolver()])
    res = chain.call("resolve", type("R", (), {"priorities": {"safetyWeight": .25, "scienceWeight": .2, "distanceWeight": .15,
                     "walkingDifficultyWeight": .15, "returnWeight": .15, "environmentWeight": .05, "roverPathWeight": .05}})())
    assert res.answered_by.kind == "ALGORITHM" and res.skipped


def test_invalid_answer_is_rejected():
    req = type("Q", (), {"height": 2, "width": 2, "routable": np.ones((2, 2), bool)})()
    bad = CostFactors(ProviderInfo("m", "MODEL", "HTTP", "1"), np.full((6, 2, 2), np.nan, np.float32), 0.4)
    with pytest.raises(Exception):
        validate_cost_factors(bad, req)


@pytest.fixture
def mock_model():
    from tools.mock_model_provider import create_app
    srv = make_server("127.0.0.1", 0, create_app())
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_routes_with_remote_model(prepared, tmp_path, mission_body, mock_model):
    """Same weights over HTTP must give the same routes as the local algorithm, and the route names the model."""
    import shutil
    from redgrid import create_app
    dbfile, data = prepared
    out = {}
    for name, cfg in (("local", {"COST_PROVIDERS": ["algorithm"]}),
                      ("model", {"COST_PROVIDERS": ["model", "algorithm"], "MODEL_COST_URL": mock_model})):
        copy = tmp_path / f"{name}.sqlite3"
        shutil.copy(dbfile, copy)
        c = create_app({"DATABASE": str(copy), "DATA_DIR": str(data), **cfg}).test_client()
        mid = c.post("/api/missions", json=mission_body).get_json()["id"]
        out[name] = c.post(f"/api/missions/{mid}/routes").get_json()
    assert out["model"][0]["costProvider"]["kind"] == "MODEL" and out["model"][0]["costModelId"] is None
    assert out["local"][0]["costProvider"]["kind"] == "ALGORITHM"
    for a, b in zip(out["local"], out["model"]):
        assert a["distanceM"] == pytest.approx(b["distanceM"], rel=0.02)   # float16 transport: near-identical paths
