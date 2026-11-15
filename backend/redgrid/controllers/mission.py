from flask import Blueprint, jsonify, request

from .. import serialize as S
from ..container import services
from . import body

bp = Blueprint("mission", __name__)


@bp.post("/missions")
def create():
    return jsonify(S.mission(services().mission.create(body()))), 201


@bp.get("/missions")
def list_():
    return jsonify([S.mission(m) for m in services().mission.list(request.args.get("status"))])


@bp.get("/missions/<int:mid>")
def get(mid):
    return jsonify(S.mission(services().mission.get(mid)))


@bp.patch("/missions/<int:mid>")
def update(mid):
    return jsonify(S.mission(services().mission.update(mid, body())))


@bp.post("/missions/<int:mid>/duplicate")
def duplicate(mid):
    return jsonify(S.mission(services().mission.duplicate(mid))), 201


@bp.patch("/missions/<int:mid>/status")
def status(mid):
    return jsonify(S.mission(services().mission.change_status(mid, body())))


@bp.get("/missions/<int:mid>/annotations")
def annotations(mid):
    return jsonify([S.annotation(a) for a in services().mission.list_annotations(mid)])


@bp.post("/missions/<int:mid>/annotations")
def add_annotation(mid):
    return jsonify(S.annotation(services().mission.add_annotation(mid, body()))), 201


@bp.delete("/missions/<int:mid>/annotations/<int:aid>")
def delete_annotation(mid, aid):
    services().mission.remove_annotation(mid, aid)
    return "", 204


@bp.get("/missions/<int:mid>/resources")
def get_resources(mid):
    return jsonify(S.resources(services().mission.get_resources(mid)))


@bp.put("/missions/<int:mid>/resources")
def set_resources(mid):
    return jsonify(S.resources(services().mission.set_resources(mid, body())))
