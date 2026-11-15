from flask import Blueprint, jsonify

from ..container import services

bp = Blueprint("report", __name__)


@bp.get("/missions/<int:mid>/report")
def report(mid):
    return jsonify(services().report.build(mid))
