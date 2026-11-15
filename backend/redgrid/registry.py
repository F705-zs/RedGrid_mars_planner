"""Which class fills each puzzle slot. Swap a piece by setting REPOSITORY_OVERRIDES / PROVIDER_OVERRIDES in the app
config to a dotted class path, e.g. {"routes": "mypkg.storage.PostgresRouteRepository"}.
Every class is checked against its interface when the app starts."""
from __future__ import annotations

import importlib
import inspect

from . import interfaces as I

REPOSITORIES = {   # slot: (default class, interface)
    "regions": ("redgrid.repositories.catalog.RegionRepository", I.RegionRepositoryI),
    "datasets": ("redgrid.repositories.catalog.DatasetRepository", I.DatasetRepositoryI),
    "layers": ("redgrid.repositories.catalog.LayerRepository", I.LayerRepositoryI),
    "constants": ("redgrid.repositories.catalog.ConstantRepository", I.ConstantRepositoryI),
    "cost_models": ("redgrid.repositories.catalog.CostModelRepository", I.CostModelRepositoryI),
    "profiles": ("redgrid.repositories.catalog.RouteProfileRepository", I.RouteProfileRepositoryI),
    "presets": ("redgrid.repositories.catalog.PriorityPresetRepository", I.PriorityPresetRepositoryI),
    "terrain_classes": ("redgrid.repositories.catalog.TerrainClassRepository", I.TerrainClassRepositoryI),
    "environment": ("redgrid.repositories.environment.EnvironmentRepository", I.EnvironmentRepositoryI),
    "missions": ("redgrid.repositories.mission.MissionRepository", I.MissionRepositoryI),
    "routes": ("redgrid.repositories.route.RouteRepository", I.RouteRepositoryI),
    "resources": ("redgrid.repositories.resource.ResourceRepository", I.ResourceRepositoryI),
    "rasters": ("redgrid.repositories.raster.RasterRepository", I.RasterRepositoryI),
}
PROVIDERS = {      # (chain, name in REDGRID_*_PROVIDERS): (default class, interface)
    ("cost", "algorithm"): ("redgrid.providers.cost.AlgorithmCostProvider", I.CostProviderI),
    ("cost", "model"): ("redgrid.providers.cost.HttpModelCostProvider", I.CostProviderI),
    ("priority", "algorithm"): ("redgrid.providers.priority.AlgorithmPriorityResolver", I.PriorityResolverI),
    ("priority", "model"): ("redgrid.providers.priority.HttpModelPriorityResolver", I.PriorityResolverI),
    ("resource", "defaults"): ("redgrid.providers.resources.DefaultResourceProvider", I.ResourceProviderI),
    ("resource", "sensor"): ("redgrid.providers.resources.SensorResourceProvider", I.ResourceProviderI),
}


def _load(path_or_class):
    if inspect.isclass(path_or_class):
        return path_or_class
    module, _, name = path_or_class.rpartition(".")
    return getattr(importlib.import_module(module), name)


def required_methods(interface) -> list[str]:
    return [n for n, v in vars(interface).items() if callable(v) and not n.startswith("_")]


def missing_methods(cls, interface) -> list[str]:
    return [m for m in required_methods(interface) if not callable(getattr(cls, m, None))]


def verify(config) -> dict:
    """Resolve every slot to a class and check it against its interface. Raises RuntimeError listing every problem."""
    problems, repos, providers = [], {}, {}
    rover = config.get("REPOSITORY_OVERRIDES") or {}
    pover = config.get("PROVIDER_OVERRIDES") or {}
    for slot in rover:
        if slot not in REPOSITORIES:
            problems.append(f"unknown repository slot '{slot}' (known: {', '.join(REPOSITORIES)})")
    for slot, (default, iface) in REPOSITORIES.items():
        try:
            cls = _load(rover.get(slot, default))
        except Exception as exc:
            problems.append(f"repository '{slot}': cannot load {rover.get(slot, default)} ({exc})")
            continue
        miss = missing_methods(cls, iface)
        if miss:
            problems.append(f"repository '{slot}' ({cls.__name__}) is missing: {', '.join(miss)}")
        repos[slot] = cls
    for key, (default, iface) in PROVIDERS.items():
        target = pover.get(f"{key[0]}.{key[1]}", default)
        try:
            cls = _load(target)
        except Exception as exc:
            problems.append(f"provider '{key[0]}.{key[1]}': cannot load {target} ({exc})")
            continue
        miss = missing_methods(cls, iface)
        if miss:
            problems.append(f"provider '{key[0]}.{key[1]}' ({cls.__name__}) is missing: {', '.join(miss)}")
        providers[key] = cls
    for chain, setting in (("cost", "COST_PROVIDERS"), ("priority", "PRIORITY_RESOLVERS"), ("resource", "RESOURCE_PROVIDERS")):
        names = config.get(setting) or []
        for n in names:
            if (chain, n) not in PROVIDERS:
                problems.append(f"{setting}: unknown provider '{n}'")
        if names and names[-1] not in ("algorithm", "defaults"):
            problems.append(f"{setting}: the last provider must be local (algorithm or defaults), found '{names[-1]}'")
    if problems:
        raise RuntimeError("RedGrid cannot start:\n  - " + "\n  - ".join(problems))
    return {"repositories": repos, "providers": providers}
