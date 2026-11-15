from flask import Blueprint, Response, jsonify, request

from ..container import services

bp = Blueprint("catalog", __name__)


@bp.get("/regions")
def regions():
    return jsonify(services().catalog.regions_json())


@bp.get("/regions/<int:rid>")
def region(rid):
    return jsonify(services().catalog.region_json(rid))


@bp.get("/regions/<int:rid>/layers")
def layers(rid):
    return jsonify(services().catalog.layers_json(rid))


@bp.get("/regions/<int:rid>/layers/<key>/geojson")
def layer_geojson(rid, key):
    return jsonify(services().catalog.layer_geojson(rid, key))


@bp.get("/regions/<int:rid>/datasets")
def datasets(rid):
    return jsonify(services().catalog.datasets_json(rid))


@bp.get("/regions/<int:rid>/terrain")
def terrain(rid):
    return jsonify(services().catalog.terrain(rid, request.args))


@bp.get("/regions/<int:rid>/terrain/texture")
def texture(rid):
    png = services().catalog.texture(rid, request.args)
    return Response(png, mimetype="image/png", headers={"Cache-Control": "public, max-age=3600"})


@bp.get("/route-profiles")
def route_profiles():
    return jsonify(services().catalog.route_profiles_json())


@bp.get("/priority-presets")
def presets():
    return jsonify(services().catalog.presets_json())


@bp.get("/categories")
def categories():
    return jsonify(services().catalog.categories_json())


@bp.get("/terrain-class-mapping")
def terrain_mapping():
    return jsonify(services().catalog.terrain_mapping_json())


@bp.get("/cost-model")
def cost_model():
    return jsonify(services().catalog.active_cost_model_json())


@bp.get("/cost-models")
def cost_models():
    return jsonify(services().catalog.cost_models_json())


@bp.get("/cost-models/<int:mid>")
def cost_model_by_id(mid):
    return jsonify(services().catalog.cost_model_json(mid))


@bp.get("/planning-constants")
def constants():
    return jsonify(services().catalog.constants_json())


@bp.get("/demo-window")
def demo_window():
    return jsonify(services().catalog.demo_window_json())


@bp.get("/providers")
def providers():
    return jsonify(services().catalog.providers_json())
