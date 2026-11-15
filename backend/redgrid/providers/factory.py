"""Builds the three provider chains from configuration (order = REDGRID_*_PROVIDERS), using the classes the registry
resolved and checked at start-up."""
from __future__ import annotations

from .chain import ProviderChain
from .contracts import validate_cost_factors, validate_group_scales


def build_chains(config, cost_models, constants, classes):
    timeout = constants.value("provider_timeout_s")
    hk = dict(health_timeout_s=config["HEALTH_TIMEOUT_S"], health_cache_s=config["HEALTH_CACHE_S"])
    cache = config.setdefault("_HTTP_PROVIDERS", {})   # keep health-check caches across requests
    urls = {("cost", "model"): config["MODEL_COST_URL"], ("priority", "model"): config["MODEL_PRIORITY_URL"],
            ("resource", "sensor"): config["SENSOR_URL"]}

    def make(chain, name):
        cls = classes[(chain, name)]
        if (chain, name) in urls:                        # remote providers: one instance per URL, reused
            key = (cls.__name__, urls[(chain, name)])
            if key not in cache:
                cache[key] = cls(urls[(chain, name)], timeout, **hk)
            return cache[key]
        if chain == "cost":
            return cls(cost_models)
        if chain == "resource":
            return cls(constants)
        return cls()

    return (ProviderChain("CostProvider", [make("cost", n) for n in config["COST_PROVIDERS"]], validate_cost_factors),
            ProviderChain("PriorityResolver", [make("priority", n) for n in config["PRIORITY_RESOLVERS"]],
                          lambda v: validate_group_scales(v)),
            ProviderChain("ResourceProvider", [make("resource", n) for n in config["RESOURCE_PROVIDERS"]]))
