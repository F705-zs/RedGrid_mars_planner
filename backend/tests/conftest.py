import math
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from redgrid import create_app, db  # noqa: E402

R = 3396190.0
LANDING = (77.45088573, 18.44462715)


def ll(east, north):
    lon0, lat0 = LANDING
    return lon0 + math.degrees(east / (R * math.cos(math.radians(lat0)))), lat0 + math.degrees(north / R)


@pytest.fixture(scope="session")
def prepared(tmp_path_factory):
    """Database + synthetic prepared data, built once per test session."""
    base = tmp_path_factory.mktemp("redgrid")
    dbfile, data = base / "seed.sqlite3", base / "data"
    app = create_app({"DATABASE": str(dbfile), "DATA_DIR": str(data), "TESTING": True})
    db.init_db(str(dbfile))
    from redgrid.demo_data import make_demo
    from redgrid.loader import load_prepared
    make_demo(str(data))
    with app.app_context():
        load_prepared(str(data), demonstration=True)
    return dbfile, data


@pytest.fixture
def app(prepared, tmp_path):
    dbfile, data = prepared
    copy = tmp_path / "test.sqlite3"
    shutil.copy(dbfile, copy)
    return create_app({"DATABASE": str(copy), "DATA_DIR": str(data), "TESTING": True})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mission_body():
    dlon, dlat = ll(-3800, 1500)
    return {"regionId": 1, "name": "Delta walk", "startLon": LANDING[0], "startLat": LANDING[1],
            "destLon": dlon, "destLat": dlat, "profile": "BALANCED"}
