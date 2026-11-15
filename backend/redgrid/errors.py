"""API errors: every failure returns {"error": {"code", "message", "details"}} (RedGrid API Contract)."""
from __future__ import annotations

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

STATUS = {
    "VALIDATION_ERROR": 400, "OUT_OF_REGION": 400, "OUT_OF_COVERAGE": 400, "INVALID_PROFILE": 400,
    "LAYER_NOT_VECTOR": 400, "LAYER_NOT_RASTER": 400,
    "REGION_NOT_FOUND": 404, "LAYER_NOT_FOUND": 404, "MISSION_NOT_FOUND": 404, "ROUTE_NOT_FOUND": 404,
    "ANNOTATION_NOT_FOUND": 404, "COST_MODEL_NOT_FOUND": 404, "NOT_FOUND": 404,
    "INVALID_STATUS_TRANSITION": 409, "MISSION_FINALIZED": 409, "ROUTE_NOT_IN_MISSION": 409,
    "ROUTES_NOT_CALCULATED": 409, "ROUTE_TOO_LONG": 400,
    "DATA_NOT_PREPARED": 503, "INTERNAL_ERROR": 500,
}


class ApiError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status = STATUS.get(code, 400)

    def to_response(self):
        return jsonify({"error": {"code": self.code, "message": self.message, "details": self.details}}), self.status


def validation(message: str, **details) -> ApiError:
    return ApiError("VALIDATION_ERROR", message, details)


def register(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api(err: ApiError):
        return err.to_response()

    @app.errorhandler(HTTPException)
    def _http(err: HTTPException):
        code = "NOT_FOUND" if err.code == 404 else ("VALIDATION_ERROR" if err.code in (400, 405, 415) else "INTERNAL_ERROR")
        return jsonify({"error": {"code": code, "message": err.description, "details": {}}}), err.code

    @app.errorhandler(Exception)
    def _any(err: Exception):
        app.logger.exception("Unhandled error")
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "Unexpected server problem", "details": {}}}), 500
