from __future__ import annotations

import json
import sqlite3

from ..errors import ApiError
from ..geo import BBox
from ..models import (Category, CategoryWeight, CostModel, Dataset, Feature, Layer, PlanningConstant,
                      PresetWeights, PriorityProfile, ProfileRule, Region, RouteProfile)


def _dataset(r) -> Dataset:
    return Dataset(id=r["id"], name=r["name"], provider=r["provider"], doi=r["doi"], url=r["url"],
                   licence=r["licence"], coverage=r["coverage"], coordinate_system=r["coordinate_system"],
                   format=r["format"], resolution_m=r["resolution_m"], accessed_on=r["accessed_on"],
                   is_training=bool(r["is_training"]))


class RegionRepository:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def _row(self, r) -> Region:
        return Region(id=r["id"], name=r["name"], bbox=BBox(r["bbox_west"], r["bbox_south"], r["bbox_east"], r["bbox_north"]),
                      coordinate_system=r["coordinate_system"], center_lon=r["center_lon"], center_lat=r["center_lat"],
                      default_zoom=r["default_zoom"],
                      routable_geometry=json.loads(r["routable_geometry_json"]) if r["routable_geometry_json"] else None)

    def get_all(self) -> list[Region]:
        return [self._row(r) for r in self.db.execute("SELECT * FROM region ORDER BY id")]

    def get_by_id(self, region_id: int) -> Region:
        r = self.db.execute("SELECT * FROM region WHERE id = ?", (region_id,)).fetchone()
        if r is None:
            raise ApiError("REGION_NOT_FOUND", f"Region {region_id} does not exist")
        return self._row(r)

    def set_routable_geometry(self, region_id: int, geometry: dict) -> None:
        self.db.execute("UPDATE region SET routable_geometry_json = ? WHERE id = ?", (json.dumps(geometry), region_id))


class DatasetRepository:
    def __init__(self, db):
        self.db = db

    def get_all(self) -> list[Dataset]:
        return [_dataset(r) for r in self.db.execute("SELECT * FROM dataset ORDER BY id")]

    def get_by_region(self, region_id: int) -> list[Dataset]:
        rows = self.db.execute("""SELECT DISTINCT d.* FROM dataset d JOIN layer l ON l.dataset_id = d.id
                                  WHERE l.region_id = ? ORDER BY d.id""", (region_id,))
        return [_dataset(r) for r in rows]

    def get_by_id(self, dataset_id: int) -> Dataset:
        r = self.db.execute("SELECT * FROM dataset WHERE id = ?", (dataset_id,)).fetchone()
        if r is None:
            raise ApiError("NOT_FOUND", f"Dataset {dataset_id} does not exist")
        return _dataset(r)

    def get_training_sources(self, model_id: int) -> list[Dataset]:
        rows = self.db.execute("""SELECT d.* FROM dataset d JOIN training_dataset_link t ON t.dataset_id = d.id
                                  WHERE t.model_id = ? ORDER BY d.id""", (model_id,))
        return [_dataset(r) for r in rows]

    def set_accessed_on(self, url: str, date: str) -> int:
        return self.db.execute("UPDATE dataset SET accessed_on = ? WHERE url = ?", (date, url)).rowcount


class LayerRepository:
    def __init__(self, db):
        self.db = db

    def _layer(self, r) -> Layer:
        ds = _dataset(self.db.execute("SELECT * FROM dataset WHERE id = ?", (r["dataset_id"],)).fetchone())
        return Layer(id=r["id"], region_id=r["region_id"], dataset=ds, key=r["key"], display_name=r["display_name"],
                     kind=r["kind"], data_state=r["data_state"], default_on=bool(r["default_on"]), raster_path=r["raster_path"])

    @staticmethod
    def _feature(r) -> Feature:
        return Feature(id=r["id"], layer_id=r["layer_id"], feature_type=r["feature_type"], name=r["name"], code=r["code"],
                       geometry=json.loads(r["geometry_json"]), science_value=r["science_value"],
                       provides_refill=bool(r["provides_refill"]), height_m=r["height_m"])

    def get_by_region(self, region_id: int) -> list[Layer]:
        return [self._layer(r) for r in self.db.execute("SELECT * FROM layer WHERE region_id = ? ORDER BY id", (region_id,))]

    def get_by_key(self, region_id: int, key: str) -> Layer:
        r = self.db.execute("SELECT * FROM layer WHERE region_id = ? AND key = ?", (region_id, key)).fetchone()
        if r is None:
            raise ApiError("LAYER_NOT_FOUND", f"Layer '{key}' does not exist in region {region_id}")
        return self._layer(r)

    def get_features(self, region_id: int, layer_key: str) -> list[Feature]:
        layer = self.get_by_key(region_id, layer_key)
        if layer.kind != "VECTOR":
            raise ApiError("LAYER_NOT_VECTOR", f"Layer '{layer_key}' is a raster layer")
        return [self._feature(r) for r in self.db.execute("SELECT * FROM feature WHERE layer_id = ? ORDER BY id", (layer.id,))]

    def get_features_by_type(self, region_id: int, feature_type: str) -> list[Feature]:
        rows = self.db.execute("""SELECT f.* FROM feature f JOIN layer l ON l.id = f.layer_id
                                  WHERE l.region_id = ? AND f.feature_type = ? ORDER BY f.id""", (region_id, feature_type))
        return [self._feature(r) for r in rows]

    def get_refill_points(self, region_id: int) -> list[Feature]:
        return [f for f in self.get_features_by_type(region_id, "SAFE_POINT") if f.provides_refill]

    def replace_features(self, layer_id: int, features: list[dict]) -> int:
        self.db.execute("DELETE FROM feature WHERE layer_id = ?", (layer_id,))
        for f in features:
            self.db.execute("""INSERT INTO feature (layer_id, feature_type, name, code, geometry_json, science_value,
                               provides_refill, height_m) VALUES (?,?,?,?,?,?,?,?)""",
                            (layer_id, f["featureType"], f.get("name"), f.get("code"), json.dumps(f["geometry"]),
                             f.get("scienceValue"), int(bool(f.get("providesRefill"))), f.get("heightM")))
        return len(features)


class ConstantRepository:
    def __init__(self, db):
        self.db = db
        self._cache: dict[str, PlanningConstant] | None = None

    def _load(self) -> dict[str, PlanningConstant]:
        if self._cache is None:
            self._cache = {r["key"]: PlanningConstant(**dict(r)) for r in self.db.execute("SELECT * FROM planning_constant ORDER BY key")}
        return self._cache

    def get_all(self) -> list[PlanningConstant]:
        return list(self._load().values())

    def get(self, key: str) -> PlanningConstant:
        try:
            return self._load()[key]
        except KeyError:
            raise ApiError("INTERNAL_ERROR", f"Planning constant '{key}' is missing from the database")

    def value(self, key: str) -> float:
        return float(self.get(key).value)


class CostModelRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _model(r) -> CostModel:
        return CostModel(id=r["id"], version=r["version"], method=r["method"], status=r["status"], trained_on=r["trained_on"],
                         training_summary=r["training_summary"], test_score=r["test_score"], created_at=r["created_at"])

    def get_active(self) -> CostModel:
        r = self.db.execute("SELECT * FROM cost_model WHERE status = 'ACTIVE'").fetchone()
        if r is None:
            raise ApiError("INTERNAL_ERROR", "No ACTIVE weight model")
        m = self._model(r)
        m.weights = self.get_weights(m.id)
        return m

    def get_by_id(self, model_id: int, with_weights: bool = True) -> CostModel:
        r = self.db.execute("SELECT * FROM cost_model WHERE id = ?", (model_id,)).fetchone()
        if r is None:
            raise ApiError("COST_MODEL_NOT_FOUND", f"Weight model {model_id} does not exist")
        m = self._model(r)
        if with_weights:
            m.weights = self.get_weights(m.id)
        return m

    def get_by_version(self, version: int) -> CostModel:
        r = self.db.execute("SELECT id FROM cost_model WHERE version = ?", (version,)).fetchone()
        return self.get_by_id(r["id"])

    def get_all(self) -> list[CostModel]:
        return [self._model(r) for r in self.db.execute("SELECT * FROM cost_model ORDER BY version")]

    def get_weights(self, model_id: int) -> list[CategoryWeight]:
        rows = self.db.execute("""SELECT w.* FROM category_weight w JOIN category c ON c.key = w.category_key
                                  WHERE w.model_id = ? ORDER BY c.bit""", (model_id,))
        return [CategoryWeight(category_key=r["category_key"], coefficient=r["coefficient"], weight=r["weight"],
                               probability=r["probability"], std_error=r["std_error"], basis=r["basis"]) for r in rows]

    def get_categories(self) -> list[Category]:
        return [Category(key=r["key"], display_name=r["display_name"], group=r["category_group"], scope=r["scope"],
                         layer_key=r["layer_key"], rule=r["rule"], is_reference=bool(r["is_reference"]), bit=r["bit"])
                for r in self.db.execute("SELECT * FROM category ORDER BY bit")]

    # --- training package only ---
    def save(self, model: CostModel, weights: list[CategoryWeight]) -> CostModel:
        cur = self.db.execute("""INSERT INTO cost_model (version, method, status, trained_on, training_summary, test_score, created_at)
                                 VALUES ((SELECT COALESCE(MAX(version), -1) + 1 FROM cost_model), ?, 'DRAFT', ?, ?, ?, ?)""",
                              (model.method, model.trained_on, model.training_summary, model.test_score, model.created_at))
        mid = cur.lastrowid
        for w in weights:
            self.db.execute("""INSERT INTO category_weight (model_id, category_key, coefficient, weight, probability, std_error, basis)
                               VALUES (?,?,?,?,?,?,?)""", (mid, w.category_key, w.coefficient, w.weight, w.probability, w.std_error, w.basis))
        return self.get_by_id(mid)

    def activate(self, model_id: int) -> None:
        with self.db:
            self.db.execute("UPDATE cost_model SET status = 'RETIRED' WHERE status = 'ACTIVE'")
            self.db.execute("UPDATE cost_model SET status = 'ACTIVE' WHERE id = ?", (model_id,))


class RouteProfileRepository:
    def __init__(self, db):
        self.db = db

    def get_rules(self, route_type: str) -> list[ProfileRule]:
        return [ProfileRule(route_type=r["route_type"], group=r["category_group"], scale=r["scale"],
                            max_factor=r["max_factor"], max_vs_hazard=r["max_vs_hazard"])
                for r in self.db.execute("SELECT * FROM profile_rule WHERE route_type = ?", (route_type,))]

    def get_by_key(self, key: str) -> RouteProfile:
        r = self.db.execute("SELECT * FROM route_profile WHERE key = ?", (key,)).fetchone()
        if r is None:
            raise ApiError("NOT_FOUND", f"Route profile {key} does not exist")
        return RouteProfile(key=r["key"], display_name=r["display_name"], distance_weight=r["distance_weight"],
                            rules=self.get_rules(key))

    def get_all(self) -> list[RouteProfile]:
        from ..enums import ROUTE_TYPES
        return [self.get_by_key(k) for k in ROUTE_TYPES]


class PriorityPresetRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _preset(r) -> PresetWeights:
        w = PriorityProfile(safetyWeight=r["safety_weight"], scienceWeight=r["science_weight"], distanceWeight=r["distance_weight"],
                            walkingDifficultyWeight=r["walking_difficulty_weight"], returnWeight=r["return_weight"],
                            environmentWeight=r["environment_weight"], roverPathWeight=r["rover_path_weight"])
        return PresetWeights(key=r["key"], display_name=r["display_name"], description=r["description"], weights=w, basis=r["basis"])

    def get_all(self) -> list[PresetWeights]:
        order = "CASE key WHEN 'BALANCED' THEN 1 WHEN 'SAFETY_FOCUSED' THEN 2 WHEN 'SCIENCE_FOCUSED' THEN 3 ELSE 4 END"
        return [self._preset(r) for r in self.db.execute(f"SELECT * FROM priority_preset ORDER BY {order}")]

    def get_by_key(self, key: str) -> PresetWeights:
        r = self.db.execute("SELECT * FROM priority_preset WHERE key = ?", (key,)).fetchone()
        if r is None:
            raise ApiError("INVALID_PROFILE", f"Unknown preset {key}")
        return self._preset(r)


class TerrainClassRepository:
    def __init__(self, db):
        self.db = db

    def get_all(self) -> list[dict]:
        rows = self.db.execute("SELECT * FROM terrain_class_mapping ORDER BY terrain_class, unit_symbol")
        return [dict(r) for r in rows]

    def class_of(self, unit_symbol: str) -> str | None:
        r = self.db.execute("SELECT terrain_class FROM terrain_class_mapping WHERE unit_symbol = ?", (unit_symbol,)).fetchone()
        return r["terrain_class"] if r else None
