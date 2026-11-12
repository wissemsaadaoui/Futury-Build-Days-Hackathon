"""Event preview (mocks/API.md §5.3) : comment le TRADING a réagi aux annonces passées du même type.

Ce n'est PAS une prédiction de prix : aucun prix cible, aucune direction de cours, aucune recommandation.
Le mouvement de prix n'apparaît qu'en valeur ABSOLUE (amplitude), jamais signé.

Chaque événement passé est mesuré par l'impact card existante (impact.py + intraday.py), sans résumé LLM.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app import etl
from app.analytics import data, events
from app.analytics._util import clean, iso, r1, r2
from app.analytics.impact import NotFound, build_impact_card

METRICS = (
    "spread_change_pct",
    "volume_ratio",
    "price_abs_change_pct",
    "sessions_to_normal",
    "auction_share_change_pts",
    "first_15min_ratio",
)
NORMAL_TOLERANCE = 1.1  # spread revenu à <= 110 % de sa baseline (même règle que assistant.facts)
NOTE = "Based on 2026 data only (Jan–Oct)."
PEERS_NOTE_EMPTY = "No peer events of this type in the event calendar"

# Règles des attention_points (constantes simples, pas de LLM)
SPREAD_WIDEN_PCT = 25.0
SLOW_NORMALISATION_SESSIONS = 2
FAST_REACTION_FIRST15 = 5.0
VS_PEERS_PTS = 10.0


def _sessions_to_normal(card: dict) -> int | None:
    """0 si le spread du jour est déjà <= 110 % de sa baseline, sinon nombre de séances avant d'y revenir
    (None si pas revenu dans la fenêtre de +5 séances)."""
    sp = card["metrics"]["spread_bps"]
    base, ev = sp.get("baseline"), sp.get("event")
    if base is None or ev is None:
        return None
    if ev <= base * NORMAL_TOLERANCE:
        return 0
    from app.assistant.facts import sessions_to_normalise  # même règle que les résumés

    return sessions_to_normalise(card, NORMAL_TOLERANCE)


def event_metrics(event_id: str) -> dict:
    """Métriques de réaction d'un événement passé, depuis son impact card (sans résumé)."""
    card = build_impact_card(event_id, with_summary=False)
    m = card["metrics"]
    price = m.get("price", {}).get("change_pct")
    it = card.get("intraday") or {}
    return {
        "event_id": event_id,
        "date": card["event"]["trading_day"],
        "spread_change_pct": m["spread_bps"].get("change_pct"),
        "volume_ratio": m.get("volume", {}).get("ratio"),
        "price_abs_change_pct": r1(abs(price)) if price is not None else None,
        "sessions_to_normal": _sessions_to_normal(card),
        "auction_share_change_pts": m.get("auction_share", {}).get("change_pts"),
        "first_15min_ratio": (it.get("first_15min") or {}).get("ratio"),
    }


def _stats(values: list, digits: int = 1) -> dict:
    """{n, median, min, max} ; median/min/max null si aucune valeur."""
    vals = [float(v) for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))]
    rnd = r1 if digits == 1 else r2
    if not vals:
        return {"n": 0, "median": None, "min": None, "max": None}
    return {"n": len(vals), "median": rnd(np.median(vals)), "min": rnd(min(vals)), "max": rnd(max(vals))}


_DIGITS = {"volume_ratio": 2, "auction_share_change_pts": 2, "first_15min_ratio": 2}


def _history(isins: list[str], event_type: str, day: pd.Timestamp | None) -> dict:
    """Événements passés du type pour ces ISIN, mesurés et résumés par métrique."""
    ev = events.events_df()
    ev = ev[ev["isin"].isin(isins) & (ev["type"] == event_type)]
    if day is not None:
        ev = ev[pd.to_datetime(ev["trading_day"]) < day]  # jamais d'événement postérieur (ou égal) à `day`
    rows = [event_metrics(e) for e in ev["event_id"]]
    out = {"n": len(rows), "events": rows}
    for k in METRICS:
        out[k] = _stats([r[k] for r in rows], _DIGITS.get(k, 1))
    return out


def _upcoming(isin: str, event_type: str, day: pd.Timestamp | None) -> dict | None:
    """Prochain événement de ce type dans events.csv (après `day`, sinon après la dernière date de données)."""
    raw = etl.load_events()
    raw = raw[(raw["isin"] == isin) & (raw["type"] == event_type)].copy()
    ref = day if day is not None else data.trading_days()[-1]
    raw["d"] = pd.to_datetime(raw["date"])
    nxt = raw[raw["d"] >= ref if day is not None else raw["d"] > ref].sort_values("d")
    if not nxt.empty:
        r = nxt.iloc[0]
        return {"date": r["date"], "title": r["title"] or None, "event_id": r["event_id"], "source_url": r["source_url"] or None}
    if day is not None:
        return {"date": iso(day), "title": None, "event_id": None, "source_url": None}
    return None


def _confidence(n: int) -> str:
    return "low" if n < 3 else ("medium" if n <= 5 else "high")


# Checklist IR : constats sur les réactions PASSÉES + préparation. Jamais de prédiction de cours.
CHECK_VOLUME_RATIO = 1.5
CHECK_SPREAD_PCT = 10.0
CHECK_FAST_SESSIONS = 1


def _checklist(own: dict, event_type: str) -> list[str]:
    from app.assistant.facts import EVENT_LABELS
    from app.assistant.templates import _noun

    releases = _noun(event_type, EVENT_LABELS.get(event_type, event_type.replace("_", " ")), 2)
    out = []
    vr = own["volume_ratio"]["median"]
    if vr is not None and vr > CHECK_VOLUME_RATIO:
        out.append(f"Past {releases} traded a median of {vr:.1f}x usual volume: inform the designated "
                   "sponsor / market makers ahead of publication.")
    sp = own["spread_change_pct"]["median"]
    if sp is not None and sp > CHECK_SPREAD_PCT:
        out.append(f"The spread widened by a median of {sp:+.1f}% on past publication days: consider publishing before "
                   "the market opens so the order book can adjust from the opening auction.")
    stn = own["sessions_to_normal"]["median"]
    if stn is not None and stn <= CHECK_FAST_SESSIONS:
        out.append(f"On past {releases} the effect on liquidity faded within one session "
                   f"(median {stn:g} session{'s' if stn != 1 else ''} to normal).")
    return out


def _attention_points(own: dict, peers: dict) -> list[str]:
    pts = []
    sp = own["spread_change_pct"]["median"]
    if sp is not None and sp > SPREAD_WIDEN_PCT:
        pts.append("Spreads typically widen markedly on this event type: consider briefing the designated sponsor / "
                   "market makers ahead of publication.")
    stn = own["sessions_to_normal"]["median"]
    if stn is not None and stn >= SLOW_NORMALISATION_SESSIONS:
        pts.append("Liquidity usually takes 2+ sessions to normalise.")
    f15 = own["first_15min_ratio"]["median"]
    if f15 is not None and f15 > FAST_REACTION_FIRST15:
        pts.append("Most of the reaction happens in the first 15 minutes after publication.")
    psp = peers["spread_change_pct"]["median"]
    if sp is not None and psp is not None and sp - psp > VS_PEERS_PTS:
        pts.append("The stock reacts more strongly than its peers.")
    return pts


def build_event_preview(isin: str, event_type: str, day=None) -> dict:
    """Réactions passées du trading aux annonces de type `event_type` (nom promis au backend : ne pas changer)."""
    if not data.known_isin(isin):
        raise NotFound(f"Unknown ISIN {isin}")
    day = pd.Timestamp(day).normalize() if day is not None else None

    own = _history([isin], event_type, day)
    peers = _history(data.peers_of(isin), event_type, day)
    peers_block = {"n": peers["n"], "events": peers["events"], **{k: peers[k] for k in METRICS}}
    if peers["n"] == 0:
        peers_block["peers_note"] = PEERS_NOTE_EMPTY

    status = {
        "spreads": "real",
        "ohlc": "real" if data.has_ohlc() else "missing",
        "flows": "real" if data.has_flows() else "missing",
        "intraday": "real" if data.has_trades(isin) else "missing",
    }
    preview = {
        "stock": {k: v for k, v in data.stock_ref(isin).items() if k != "sector"},
        "event_type": event_type,
        "as_of": iso(data.trading_days()[-1]),  # dernière date des données
        "reference_date": iso(day) if day is not None else None,  # `date` demandé : événements AVANT cette date
        "upcoming": _upcoming(isin, event_type, day),
        "own_history": own,
        "peers": peers_block,
        "attention_points": _attention_points(own, peers),
        "checklist": _checklist(own, event_type),
        "confidence": _confidence(own["n"]),
        "note": NOTE,
        "ai_summary": "",
        "_data_status": status,
    }
    preview = clean(preview)

    from app.assistant import summarize_event_preview  # import tardif (évite les imports circulaires)

    preview["ai_summary"] = summarize_event_preview(preview)
    from app.assistant import points_event_preview

    preview["ai_points"] = points_event_preview(preview)
    from app.analytics import decisions

    preview["ai_summary_id"] = f"preview:{isin}:{event_type}:{preview['reference_date'] or 'all'}"
    preview["ai_summary_decision"] = decisions.summary_decision(isin, preview["ai_summary_id"])
    return preview
