"""Sélection des faits envoyés au LLM : uniquement les parties calculées sur des données RÉELLES."""
from __future__ import annotations

from typing import Any

EVENT_LABELS = {
    "quarterly_results": "quarterly results",
    "annual_results": "annual results",
    "ad_hoc": "ad hoc announcement",
    "dividend": "dividend announcement",
    "press_release": "press release",
    "m_and_a": "M&A announcement",
    "agm": "annual general meeting",
    "index_change": "index change",
}


def sessions_to_normalise(card: dict, tolerance: float = 1.1) -> int | None:
    """Nombre de séances après l'événement avant que le spread revienne à <= 110 % de sa baseline."""
    base = card["metrics"]["spread_bps"].get("baseline")
    if not base:
        return None
    for w in card.get("window", []):
        if w["offset"] > 0 and w.get("spread_bps") is not None and w["spread_bps"] <= base * tolerance:
            return w["offset"]
    return None


def impact_facts(card: dict) -> dict[str, Any]:
    st = card.get("_data_status", {})
    ev = card.get("event")
    m = card["metrics"]
    f: dict[str, Any] = {
        "company": card["stock"]["name"],
        "index_on_day": card["stock"]["index"],
        "event": ev["title"] if ev else "unusual trading day (no announcement)",
        "event_type": EVENT_LABELS.get(ev["type"], ev["type"]) if ev else None,
        "trading_day": ev["trading_day"] if ev else (card["window"][len(card["window"]) // 2]["date"] if card.get("window") else None),
        "baseline": card["baseline"]["method"],
        "spread_bps_25k_eur": {
            "event_day": m["spread_bps"]["event"],
            "baseline": m["spread_bps"]["baseline"],
            "change_pct": m["spread_bps"]["change_pct"],
            "sessions_until_back_to_normal": sessions_to_normalise(card),
        },
    }
    if st.get("ohlc") == "real":
        f["volume"] = {"ratio_vs_baseline": m["volume"]["ratio"], "z_score": m["volume"].get("z_score")}
        f["price"] = {"change_pct": m["price"]["change_pct"], "intraday_range_pct": m["price"]["intraday_range_pct"]}
        f["peers"] = {
            "peer_median_price_change_pct": card["vs_peers"]["peer_avg_price_change_pct"],
            "excess_return_vs_peers_pct": card["vs_peers"]["excess_return_pct"],
        }
        f["technical_context"] = card.get("technical_context")
    if st.get("flows") == "real":
        f["auction_share"] = m["auction_share"]
        f["net_volume_by_participant"] = {p["type"]: p["net"] for p in card["flows"]["by_participant"]}
    return {k: v for k, v in f.items() if v is not None}


def report_facts(report: dict) -> dict[str, Any]:
    secs = {s["title"]: s for s in report["sections"]}
    return {
        "company": report["stock"]["name"],
        "period": report["period"],
        "trading_profile": [
            {"label": k["label"], "value": k["value"], "unit": k["unit"], "change_vs_previous_period_pct": k.get("change_pct")}
            for k in secs.get("Trading profile", {}).get("kpis", [])
        ],
        "peer_comparison": secs.get("Peer comparison", {}).get("kpis", []),
        "notable_events": len(secs.get("Notable events", {}).get("items", [])),
    }
