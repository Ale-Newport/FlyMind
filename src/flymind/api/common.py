"""Shared API helpers: big-integer-safe JSON, dataset access, error mapping."""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
from fastapi import HTTPException
from fastapi.encoders import ENCODERS_BY_TYPE
from fastapi.responses import JSONResponse

from flymind.common.paths import validate_identifier
from flymind.connectome.store import ConnectomeStore, DatasetNotFoundError, get_store

JS_SAFE_INT = 2**53 - 1

# Let FastAPI's encoder handle NumPy scalars/arrays returned by route handlers;
# SafeJSONResponse then stringifies integers beyond 2**53.
for _t in (np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64):
    ENCODERS_BY_TYPE[_t] = int
for _t in (np.float16, np.float32, np.float64):
    ENCODERS_BY_TYPE[_t] = float
ENCODERS_BY_TYPE[np.bool_] = bool
ENCODERS_BY_TYPE[np.ndarray] = lambda a: a.tolist()


def jsonable(obj: Any) -> Any:
    """Convert to JSON-safe values. Integers beyond 2**53 (FlyWire root IDs) become strings so
    that JavaScript clients never round them; NaN/inf become null."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [jsonable(v) for v in obj]
    if isinstance(obj, bool | np.bool_):
        return bool(obj)
    if isinstance(obj, int | np.integer):
        v = int(obj)
        return str(v) if abs(v) > JS_SAFE_INT else v
    if isinstance(obj, float | np.floating):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, np.ndarray):
        return jsonable(obj.tolist())
    if obj is None or isinstance(obj, str):
        return obj
    if hasattr(obj, "model_dump"):
        return jsonable(obj.model_dump())
    return str(obj)


class SafeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(jsonable(content), separators=(",", ":"), allow_nan=False).encode()


def store_or_404(dataset_id: str) -> ConnectomeStore:
    try:
        validate_identifier(dataset_id, "dataset id")
        return get_store(dataset_id)
    except (DatasetNotFoundError, ValueError) as exc:
        raise HTTPException(
            404,
            detail={
                "error": "dataset_not_installed",
                "dataset_id": dataset_id,
                "message": f"Dataset {dataset_id!r} is not installed. "
                "See GET /api/sources for how to install it.",
                "cause": str(exc),
            },
        ) from None


def parse_root_ids(raw: str | None, limit: int = 5000) -> list[int]:
    if not raw:
        return []
    out = []
    for tok in raw.replace(";", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        if not tok.lstrip("-").isdigit():
            raise HTTPException(422, detail=f"invalid root id {tok!r}")
        out.append(int(tok))
        if len(out) > limit:
            raise HTTPException(422, detail=f"too many ids (max {limit})")
    return out


def clean(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def neuron_record(store: ConnectomeStore, i: int) -> dict:
    nb = store.neurons
    row = nb.iloc[int(i)]
    rec = {k: clean(row[k]) for k in nb.columns}
    rec["root_id"] = str(int(row["root_id"]))
    rec["idx"] = int(row["idx"])
    for k in ("pos_x", "pos_y", "pos_z"):
        rec[k] = clean(float(row[k])) if rec.get(k) is not None else None
    return rec
