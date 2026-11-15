from flask import Blueprint, jsonify

from ..container import services
from . import float_arg

bp = Blueprint("location", __name__)


@bp.get("/regions/<int:rid>/location")
def location(rid):
    return jsonify(services().location.location(rid, float_arg("lon"), float_arg("lat")))
