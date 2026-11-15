"""Binary arrays inside JSON: {"dtype","shape","byteOrder":"little","encoding":"zlib+base64","data"} (RedGrid API Contract, Appendix A)."""
from __future__ import annotations

import base64
import zlib

import numpy as np

ALLOWED = {"uint8", "uint32", "float16", "float32"}


def encode(a: np.ndarray, dtype: str | None = None) -> dict:
    dtype = dtype or str(a.dtype)
    if dtype == "bool":
        dtype = "uint8"
    if dtype not in ALLOWED:
        raise ValueError(f"dtype {dtype} not allowed")
    raw = np.ascontiguousarray(a.astype(np.dtype(dtype).newbyteorder("<"))).tobytes()
    return {"dtype": dtype, "shape": list(a.shape), "byteOrder": "little", "encoding": "zlib+base64",
            "data": base64.b64encode(zlib.compress(raw, 6)).decode("ascii")}


def decode(d: dict) -> np.ndarray:
    if d.get("encoding") != "zlib+base64" or d.get("byteOrder", "little") != "little" or d.get("dtype") not in ALLOWED:
        raise ValueError("unsupported array encoding")
    raw = zlib.decompress(base64.b64decode(d["data"]))
    a = np.frombuffer(raw, dtype=np.dtype(d["dtype"]).newbyteorder("<"))
    return a.reshape(d["shape"]).astype(np.dtype(d["dtype"]).newbyteorder("="))
