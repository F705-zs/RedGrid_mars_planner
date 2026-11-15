"""ReportService: the one-page summary (RedGrid API Contract, Report)."""
from __future__ import annotations

from .. import serialize as S
from ..errors import ApiError

NOTICE = "Prototype human-mobility, oxygen and battery assumptions; not official NASA EVA limits."
TERRAIN_CAVEAT = ("Terrain class comes from a 1:75,000 geologic map offset by 100-200 m from the Mars 2020 base maps; "
                  "it changes walking energy by 0.91x to 1.91x.")


class ReportService:
    def __init__(self, *, missions, routes, datasets, cost_models, constants, catalog, environment, mission_service):
        self.missions, self.routes, self.datasets, self.cost_models = missions, routes, datasets, cost_models
        self.k, self.catalog, self.environment, self.mission_service = constants, catalog, environment, mission_service

    def build(self, mission_id: int) -> dict:
        m = self.missions.get_by_id(mission_id)
        routes = self.routes.get_by_mission(mission_id)
        if not routes:
            raise ApiError("ROUTES_NOT_CALCULATED", "Calculate routes before building the report")
        if m.selected_route_id:
            rec = next((r for r in routes if r["id"] == m.selected_route_id), None)
        else:
            feas = [r for r in routes if r["feasible"]]
            rec = max(feas, key=lambda r: (r["missionMatch"], r["routeType"] == "MISSION_PRIORITY")) if feas else None
        model_id = (rec or routes[0])["costModelId"]
        model = self.cost_models.get_by_id(model_id) if model_id else self.cost_models.get_active()
        providers = []
        for r in routes:
            for p in (r["costProvider"], r["priorityResolver"]):
                if p not in providers:
                    providers.append(p)
        snap = self.mission_service.get_resources(mission_id)
        providers += [p for p in snap.providers if p not in providers]
        caveats = [TERRAIN_CAVEAT]
        if any(c.data_state == "DEMONSTRATION_DATA" for c in self.k.get_all()):
            caveats.append("Several thresholds and defaults are prototype placeholders; each constant names its source.")
        return {
            "mission": S.mission(m), "routes": routes, "recommendedRoute": rec,
            "annotations": [S.annotation(a) for a in self.missions.get_annotations(mission_id)],
            "sources": [S.dataset(d) for d in self.datasets.get_by_region(m.region_id) if not d.is_training],
            "costModel": S.cost_model(model, self.datasets.get_training_sources(model.id)),
            "trainingSources": [S.dataset(d) for d in self.datasets.get_training_sources(model.id)],
            "providersUsed": providers,
            "constants": [S.constant(c) for c in self.k.get_all()],
            "terrainClassMapping": self.catalog.terrain_mapping_json(),
            "demoWindow": self.catalog.demo_window_json(),
            "resources": S.resources(snap),
            "caveats": caveats, "notice": NOTICE,
        }
