"""Petits utilitaires : arrondis, nettoyage JSON, mocks."""
from __future__ import annotations

import copy
import json
import math
from datetime import date, datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app import config


def _num(x: Any) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def r0(x: Any) -> int | None:
    f = _num(x)
    return None if f is None else int(round(f))


def r1(x: Any) -> float | None:
    f = _num(x)
    return None if f is None else round(f, 1)


def r2(x: Any) -> float | None:
    f = _num(x)
    return None if f is None else round(f, 2)


def pct(new: Any, old: Any) -> float | None:
    """Variation en % de old vers new."""
    n, o = _num(new), _num(old)
    if n is None or o is None or o == 0:
        return None
    return (n / o - 1.0) * 100.0


def ratio(a: Any, b: Any) -> float | None:
    x, y = _num(a), _num(b)
    if x is None or y is None or y == 0:
        return None
    return x / y


def iso(d: Any) -> str | None:
    if d is None or (isinstance(d, float) and math.isnan(d)):
        return None
    return pd.Timestamp(d).strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now(ZoneInfo(config.TZ)).isoformat(timespec="seconds")


def clean(obj: Any) -> Any:
    """Rend un objet sérialisable en JSON : NaN/inf -> None, numpy -> Python, dates -> str."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return _num(obj)
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return iso(obj)
    return obj


@lru_cache(maxsize=None)
def _mock_raw(name: str) -> dict:
    return json.loads((config.MOCKS_DIR / f"{name}.json").read_text(encoding="utf-8"))


def load_mock(name: str) -> dict:
    """Copie profonde d'un mock (sans les champs _endpoint/_note)."""
    d = copy.deepcopy(_mock_raw(name))
    return {k: v for k, v in d.items() if not k.startswith("_")}
