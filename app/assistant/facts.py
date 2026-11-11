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
    "voting_rights": "voting rights notification",
    "directors_dealings": "directors' dealings notification",
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


def _event_day(card: dict) -> str | None:
    ev = card.get("event")
    if ev:
        return ev["trading_day"]
    w0 = [w for w in card.get("window", []) if w.get("offset") == 0]
    return w0[0]["date"] if w0 else None


def day_alert_facts(isin: str, day: str | None, limit: int = 3) -> list[dict]:
    """Alertes d'exécution du jour (réelles), les plus fortes d'abord. Textes déjà rédigés sans « investor »."""
    if not day:
        return []
    import pandas as pd

    from app.analytics import alerts

    try:
        rows = alerts.day_alerts(isin, pd.Timestamp(day))
    except Exception:  # l'assistant ne doit jamais faire planter la carte
        return []
    rows.sort(key=lambda a: (a["severity"] != "high", -abs(a["value"] or 0)))
    return [{"type": a["type"], "severity": a["severity"], "description": a["description"]} for a in rows[:limit]]


def impact_facts(card: dict) -> dict[str, Any]:
    st = card.get("_data_status", {})
    ev = card.get("event")
    m = card["metrics"]
    f: dict[str, Any] = {
        "company": card["stock"]["name"],
        "index_on_day": card["stock"]["index"],
        "event": ev["title"] if ev else "unusual trading day (no announcement)",
        "event_type": EVENT_LABELS.get(ev["type"], ev["type"]) if ev else None,
        "trading_day": _event_day(card),
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
        a = m["auction_share"]
        pct_ = lambda x: None if x is None else round(x * 100, 1)  # noqa: E731 – en %, pour que le texte cite des nombres présents
        f["auction_share_pct"] = {"event_day": pct_(a.get("event")), "baseline": pct_(a.get("baseline"))}
        f["net_volume_by_participant"] = {p["type"]: p["net"] for p in card["flows"]["by_participant"]}
    if st.get("opening_closing_auction") == "real":
        f["auctions"] = {
            "opening_auction_ratio_vs_baseline": m["opening_auction"]["ratio"],
            "closing_auction_ratio_vs_baseline": m["closing_auction"]["ratio"],
        }
    it = card.get("intraday")
    if st.get("intraday") == "real" and it:
        f["intraday"] = {
            "reference": ("publication at " if it["during_session"] else "market open at ") + it["reference_time"][11:16],
            "announcement_during_session": it["during_session"],
            "first_15min_volume_ratio_vs_same_time_20d": it["first_15min"]["ratio"],
            "price_change_pct": it["price_change_pct"],
        }
    if st.get("ohlc") == "real":
        alerts = day_alert_facts(card["stock"]["isin"], f.get("trading_day"))
        if alerts:
            f["execution_alerts_that_day"] = alerts
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


def preview_facts(preview: dict) -> dict[str, Any]:
    """Faits de l'event preview : uniquement des statistiques de réactions PASSÉES (aucune projection)."""
    own = preview["own_history"]
    label = EVENT_LABELS.get(preview["event_type"], preview["event_type"])
    f: dict[str, Any] = {
        "company": preview["stock"]["name"],
        "event_type": label,
        "past_events_n": own["n"],
        "data_note": preview.get("note"),
        "confidence": preview.get("confidence"),
    }
    for k in ("spread_change_pct", "volume_ratio", "price_abs_change_pct", "sessions_to_normal", "first_15min_ratio"):
        st = own.get(k) or {}
        if st.get("n"):
            f[k] = {"median": st["median"], "min": st["min"], "max": st["max"], "n": st["n"]}
    f["peer_events_n"] = preview["peers"]["n"]
    if preview["peers"]["n"]:
        f["peers_spread_change_pct"] = preview["peers"]["spread_change_pct"]
    return f
