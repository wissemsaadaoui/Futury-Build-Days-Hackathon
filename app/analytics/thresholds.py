"""Seuils d'alerte modifiables par l'équipe IR (par ISIN), appliqués par toute l'analytique.

Défauts = valeurs du code (app/config.py, app/analytics/metrics.py). Les valeurs personnalisées sont dans
data/decisions.db (app/store.py). Chaque changement est inscrit dans le journal des décisions (threshold_changed).

Lecture : current(isin) -> dict complet (défauts + personnalisations), avec un petit cache invalidé à chaque écriture.
Aperçu sans enregistrer : `with override(isin, values): ...` (variable de contexte, n'affecte pas les autres requêtes).
Les fonctions mises en cache (alerts.py) reçoivent les valeurs en paramètre : un seuil différent = une autre clé
de cache, jamais de résultat périmé.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from app import config, store

# key -> défaut, bornes, pas, unité, libellé, groupe. Les pourcentages d'ADTV sont exprimés en % (10 = 10 %).
SPEC: dict[str, dict] = {
    "volume_z_min": {"default": 2.0, "min": 1.0, "max": 5.0, "step": 0.1, "unit": "z-score",
                     "label": "Volume anomaly: z-score above", "group": "anomaly", "integer": False},
    "spread_z_min": {"default": 3.0, "min": 1.0, "max": 6.0, "step": 0.1, "unit": "z-score",
                     "label": "Spread anomaly: z-score above", "group": "anomaly", "integer": False},
    "spread_ratio_min": {"default": 1.2, "min": 1.0, "max": 3.0, "step": 0.05, "unit": "× baseline",
                         "label": "Spread anomaly: and spread above", "group": "anomaly", "integer": False},
    "large_trade_adtv_pct": {"default": config.ALERT_LARGE_TRADE_ADTV_SHARE * 100, "min": 1.0, "max": 100.0, "step": 1.0,
                             "unit": "% of ADTV", "label": "Large single execution: at least", "group": "alert",
                             "integer": False},
    "sweep_min_trades": {"default": float(config.ALERT_SWEEP_MIN_TRADES), "min": 2.0, "max": 20.0, "step": 1.0,
                         "unit": "executions", "label": "Aggressor sweep: at least", "group": "alert", "integer": True},
    "sweep_adtv_pct": {"default": config.ALERT_SWEEP_ADTV_SHARE * 100, "min": 1.0, "max": 100.0, "step": 1.0,
                       "unit": "% of ADTV", "label": "Aggressor sweep: together at least", "group": "alert",
                       "integer": False},
    "net_flow_adtv_pct": {"default": config.ALERT_NET_FLOW_ADTV_SHARE * 100, "min": 5.0, "max": 200.0, "step": 1.0,
                          "unit": "% of ADTV", "label": "Unusual net flow: above", "group": "alert", "integer": False},
    "auction_spike_ratio": {"default": config.ALERT_AUCTION_SPIKE_RATIO, "min": 1.2, "max": 10.0, "step": 0.1,
                            "unit": "× baseline", "label": "Closing auction spike: share above", "group": "alert",
                            "integer": False},
}

_override: ContextVar[dict[str, dict[str, float]] | None] = ContextVar("thresholds_override", default=None)
_cache: dict[str, dict[str, float]] = {}


class InvalidThresholds(ValueError):
    """Valeur hors bornes ou clé inconnue -> 422 côté API."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def defaults() -> dict[str, float]:
    return {k: round(float(s["default"]), 4) for k, s in SPEC.items()}


def stored(isin: str) -> dict[str, float]:
    if isin not in _cache:
        _cache[isin] = {k: v for k, v in store.get_thresholds(isin).items() if k in SPEC}
    return _cache[isin]


def current(isin: str) -> dict[str, float]:
    """Seuils appliqués à cet ISIN : défauts, puis valeurs enregistrées, puis éventuel aperçu (override)."""
    out = {**defaults(), **stored(isin)}
    ov = _override.get()
    if ov and isin in ov:
        out.update(ov[isin])
    return out


def is_custom(isin: str) -> bool:
    d = defaults()
    return any(abs(v - d[k]) > 1e-9 for k, v in stored(isin).items())


def validate(values: dict[str, float]) -> dict[str, float]:
    errors, clean = {}, {}
    for k, v in values.items():
        s = SPEC.get(k)
        if s is None:
            errors[k] = "unknown threshold"
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            errors[k] = "not a number"
            continue
        if x != x or not (s["min"] <= x <= s["max"]):
            errors[k] = f"must be between {s['min']:g} and {s['max']:g}"
            continue
        if s["integer"] and x != int(x):
            errors[k] = "must be a whole number"
            continue
        clean[k] = round(x, 4)
    if errors:
        raise InvalidThresholds(errors)
    return clean


def invalidate(isin: str | None = None) -> None:
    if isin is None:
        _cache.clear()
    else:
        _cache.pop(isin, None)


def save(isin: str, values: dict[str, float], by: str) -> list[dict]:
    """Enregistre les seuils modifiés et inscrit chaque changement (ancien -> nouveau) dans le journal."""
    new = validate(values)
    old = current(isin)
    changed = {k: v for k, v in new.items() if abs(v - old[k]) > 1e-9}
    d = defaults()
    to_store = {k: v for k, v in changed.items() if abs(v - d[k]) > 1e-9}
    back_to_default = [k for k, v in changed.items() if abs(v - d[k]) <= 1e-9]
    if to_store:
        store.set_thresholds(isin, to_store, by)
    if back_to_default:
        store.delete_thresholds(isin, back_to_default)
    log = [store.add_decision("threshold", k, isin, "threshold_changed", by, note=SPEC[k]["label"],
                              old_value=f"{old[k]:g}", new_value=f"{v:g}") for k, v in changed.items()]
    invalidate(isin)
    return log


def reset(isin: str, by: str) -> list[dict]:
    return save(isin, defaults(), by)


@contextmanager
def override(isin: str, values: dict[str, float]) -> Iterator[None]:
    """Aperçu : applique ces seuils (validés) pendant le bloc, sans rien enregistrer."""
    clean = validate(values)
    token = _override.set({**(_override.get() or {}), isin: clean})
    try:
        yield
    finally:
        _override.reset(token)


def spec() -> dict[str, dict]:
    return {k: {kk: vv for kk, vv in s.items() if kk != "default"} | {"default": defaults()[k]} for k, s in SPEC.items()}
