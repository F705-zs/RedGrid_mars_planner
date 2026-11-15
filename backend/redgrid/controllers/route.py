from flask import Blueprint, jsonify

from .. import serialize as S
from ..container import services
from ..errors import validation
from . import body

bp = Blueprint("route", __name__)


@bp.post("/missions/<int:mid>/routes")
def compute(mid):
    return jsonify(services().route.compute_routes(mid)), 201


@bp.get("/missions/<int:mid>/routes")
def get(mid):
    return jsonify(services().route.get_routes(mid))


@bp.post("/missions/<int:mid>/routes/recalculate")
def recalculate(mid):
    return jsonify(services().route.recalculate(mid))


@bp.put("/missions/<int:mid>/selected-route")
def select(mid):
    rid = body().get("routeId")
    if not isinstance(rid, int) or isinstance(rid, bool):
        raise validation("routeId must be a whole number", field="routeId")
    return jsonify(S.mission(services().route.select_route(mid, rid)))
