"""GET /stocks : tous les émetteurs de l'univers DAX / MDAX / SDAX, avec ce que les données couvrent pour chacun.

pbb (config.DEMO_ISINS[0]) reste l'émetteur par défaut (is_selected) et apparaît en premier.
"""
from __future__ import annotations

import copy
from functools import lru_cache

from app import config, etl
from app.analytics import data
from app.analytics._util import clean, iso

INDEX_ORDER = {"DAX": 0, "MDAX": 1, "SDAX": 2}


def index_history(isin: str) -> list[dict]:
    """Périodes d'appartenance aux indices d'après la colonne Index du XLM : [{index, from, until}]."""
    s = data.index_series(isin).dropna()
    if s.empty:
        return []
    out = []
    for idx, grp in s.groupby((s != s.shift()).cumsum()):
        out.append({"index": str(grp.iloc[0]), "from": iso(grp.index[0]), "until": iso(grp.index[-1])})
    return out


def coverage(isin: str) -> dict:
    """Ce que l'outil peut afficher pour cet émetteur, d'après les données réellement chargées."""
    n = data.spread_sessions(isin)
    return {
        "dashboard": n >= data.MIN_SESSIONS,  # sinon le dashboard renvoie 404 avec un message clair
        "events": data.has_events(isin),  # annonces dans data/events.csv
        "intraday": data.has_trades(isin),  # trades horodatés (data/processed/trades_<ISIN>.csv.gz)
        "sessions": n,  # séances avec un spread XLM mesuré
    }


def list_stocks() -> dict:
    """~0,8 s au premier appel (174 émetteurs), puis en cache : les données ne changent pas pendant que l'API tourne."""
    return copy.deepcopy(_list_stocks())


@lru_cache(maxsize=1)
def _list_stocks() -> dict:
    u = etl.get_universe()
    if u.empty:
        return {"stocks": []}
    default = config.DEMO_ISINS[0]
    stocks = []
    for r in u.itertuples():
        hist = index_history(r.isin)
        stocks.append({
            "isin": r.isin,
            "name": data.name_of(r.isin),
            "ticker": r.mnemonic,
            "index": r.index,
            "index_history": hist if len(hist) > 1 else None,  # seulement si l'émetteur a changé d'indice
            "sector": r.sector or "",
            "market_cap_eur": None,
            "is_selected": r.isin == default,
            "peers": [p for p in config.PEERS.get(r.isin, []) if p != r.isin],
            "peer_basis": data.peer_basis(r.isin),
            "coverage": coverage(r.isin),
        })
    stocks.sort(key=lambda s: (not s["is_selected"], INDEX_ORDER.get(s["index"], 3), s["name"].lower()))
    return clean({"stocks": stocks, "default_isin": default})
