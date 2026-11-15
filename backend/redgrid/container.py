"""Builds repositories, provider chains and services for the current request (cached on flask.g)."""
from __future__ import annotations

from types import SimpleNamespace

from flask import current_app, g

from .db import get_db
from .providers.factory import build_chains
from .services.catalog_service import CatalogService
from .services.category_extractor import CategoryExtractor
from .services.location_service import LocationService
from .services.mission_service import MissionService
from .services.report_service import ReportService
from .services.route_service import RouteService


def services() -> SimpleNamespace:
    if "svc" in g:
        return g.svc
    db = get_db()
    cfg = current_app.config
    R = current_app.extensions["redgrid"]["repositories"]   # classes resolved and checked at start-up
    regions, datasets, layers = R["regions"](db), R["datasets"](db), R["layers"](db)
    constants, cost_models = R["constants"](db), R["cost_models"](db)
    profiles, presets, terrain = R["profiles"](db), R["presets"](db), R["terrain_classes"](db)
    environment, missions, routes, resources = R["environment"](db), R["missions"](db), R["routes"](db), R["resources"](db)
    rasters = R["rasters"](cfg["DATA_DIR"], layers)
    cost_chain, prio_chain, res_chain = build_chains(cfg, cost_models, constants, current_app.extensions["redgrid"]["providers"])

    class LazyExtractor:   # reads the category table only when a request needs it
        def __init__(self):
            self._x = None

        def __getattr__(self, name):
            if name == "_x":
                raise AttributeError(name)
            if self._x is None:
                self._x = CategoryExtractor(rasters, layers, cost_models, constants)
            return getattr(self._x, name)

    extractor = LazyExtractor()
    mission_svc = MissionService(missions=missions, regions=regions, presets=presets, resources=resources, constants=constants,
                                 resource_chain=res_chain)
    catalog = CatalogService(regions=regions, datasets=datasets, layers=layers, rasters=rasters, profiles=profiles, presets=presets,
                             terrain_classes=terrain, cost_models=cost_models, constants=constants, environment=environment,
                             chains=(cost_chain, prio_chain, res_chain))
    route_svc = RouteService(regions=regions, missions=missions, routes=routes, profiles=profiles, constants=constants, layers=layers,
                             rasters=rasters, environment=environment, cost_models=cost_models, extractor=extractor,
                             cost_chain=cost_chain, priority_chain=prio_chain, mission_service=mission_svc)
    g.svc = SimpleNamespace(catalog=catalog, location=LocationService(regions=regions, layers=layers, rasters=rasters,
                                                                      environment=environment, extractor=extractor),
                            mission=mission_svc, route=route_svc,
                            report=ReportService(missions=missions, routes=routes, datasets=datasets, cost_models=cost_models,
                                                 constants=constants, catalog=catalog, environment=environment, mission_service=mission_svc))
    return g.svc
