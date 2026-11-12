"""Human-in-the-loop (points 9 et 10) : identifiants stables, décision de l'équipe IR, rang du top 5.

« AI suggests, the IR team decides – every decision is logged. »
- Chaque anomalie / alerte a un `id` stable (date | type | empreinte de la description) et un `item_type`
  (`anomaly` pour volume / spread, `alert` pour les exécutions, flux et enchères).
- `decision` = dernière décision approved / dismissed de l'équipe pour cet élément (data/decisions.db), sinon None.
- `rank` : 1 = la plus importante (sévérité, puis la plus récente), calculé SANS les éléments dismissed
  (rank None pour eux) : le top 5 n'affiche jamais une alerte écartée par l'équipe.
"""
from __future__ import annotations

import hashlib

from app import store

SIGNAL_TYPES = {"volume_spike", "spread_widening", "price_move"}
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
PUBLIC_FIELDS = ("id", "decision", "note", "decided_at", "decided_by")


def item_type(anomaly_type: str) -> str:
    return "anomaly" if anomaly_type in SIGNAL_TYPES else "alert"


def anomaly_id(row: dict) -> str:
    digest = hashlib.sha1(row["description"].encode("utf-8")).hexdigest()[:8]
    return f"{row['date']}|{row['type']}|{digest}"


def public(decision: dict | None) -> dict | None:
    return None if decision is None else {k: decision.get(k) for k in PUBLIC_FIELDS}


def attach(isin: str, rows: list[dict]) -> list[dict]:
    """Ajoute id, item_type, decision et rank à chaque anomalie / alerte (en place)."""
    latest = store.latest_decisions(isin, ("alert", "anomaly"))
    for r in rows:
        r["id"] = anomaly_id(r)
        r["item_type"] = item_type(r["type"])
        r["decision"] = public(latest.get((r["item_type"], r["id"])))
    ranked = sorted(
        (r for r in rows if not (r["decision"] and r["decision"]["decision"] == "dismissed")),
        key=lambda r: (SEVERITY_RANK.get(r["severity"], 3), _neg_date(r["date"])),
    )
    ranks = {id(r): i + 1 for i, r in enumerate(ranked)}
    for r in rows:
        r["rank"] = ranks.get(id(r))
    return rows


def _neg_date(d: str) -> str:
    # tri décroissant sur une date ISO dans une clé croissante
    return "".join(chr(0x10FFFF - ord(c)) for c in d)


def summary_decision(isin: str, summary_id: str) -> dict | None:
    return public(store.latest_decisions(isin, ("ai_summary",)).get(("ai_summary", summary_id)))
