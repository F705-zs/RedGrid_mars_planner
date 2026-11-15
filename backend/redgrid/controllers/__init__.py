"""Controllers: receive the request, check the input shape, call one service method, return JSON."""
from flask import request

from ..errors import validation


def body() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        if request.data:
            raise validation("The request body must be valid JSON")
        return {}
    if not isinstance(data, dict):
        raise validation("The request body must be a JSON object")
    return data


def float_arg(name: str) -> float:
    v = request.args.get(name)
    try:
        return float(v)
    except (TypeError, ValueError):
        raise validation(f"{name} must be a number", field=name)
