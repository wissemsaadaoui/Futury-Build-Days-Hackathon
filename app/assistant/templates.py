"""Résumés de secours (sans LLM) : déterministes, toujours disponibles."""
from __future__ import annotations

from app.assistant.facts import impact_facts


def ev_is_title(f: dict) -> bool:
    """True si l'événement est une vraie annonce (et pas un jour inhabituel sans annonce)."""
    return f.get("event_type") is not None


def _f(x: float | None, nd: int = 1) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def impact_summary(card: dict) -> str:
    f = impact_facts(card)
    sp = f["spread_bps_25k_eur"]
    who = f["company"]
    what = f["event"]
    parts: list[str] = []

    if "volume" in f and "price" in f:
        parts.append(
            f"On the day of the event ({what}), {who} traded {_f(f['volume']['ratio_vs_baseline'])}x its usual volume "
            f"and the share price moved {_f(f['price']['change_pct'])}%."
        )
        ex = f.get("peers", {}).get("excess_return_vs_peers_pct")
        if ex is not None:
            parts.append(f"This is {_f(abs(ex))} percentage points {'better' if ex >= 0 else 'worse'} than the median of its peers.")
    if sp.get("event_day") is not None and sp.get("baseline") is not None:
        direction = "widened" if (sp.get("change_pct") or 0) > 0 else "tightened"
        subject = "the round-trip cost" if parts else f"{who}'s round-trip cost"
        lead = "" if parts else (f"On the {what.lower()}, " if not ev_is_title(f) else f"Following the event \"{what}\", ")
        sentence = (
            f"{lead}{subject} for a 25,000 EUR trade {direction} to {_f(sp['event_day'])} bps "
            f"versus a 20-day average of {_f(sp['baseline'])} bps ({_f(sp.get('change_pct'))}%)."
        )
        parts.append(sentence[0].upper() + sentence[1:])
        n = sp.get("sessions_until_back_to_normal")
        if n is not None:
            parts.append(f"Liquidity returned to its normal level after {n} session{'s' if n > 1 else ''}.")

    if "auction_share" in f:
        a = f["auction_share"]
        parts.append(f"Auctions accounted for {_f((a.get('event') or 0) * 100)}% of volume versus {_f((a.get('baseline') or 0) * 100)}% normally.")
    return " ".join(parts)


def profile_text(kpis: list[dict]) -> str:
    parts = []
    for k in kpis:
        if k.get("change_pct") is None:
            continue
        parts.append(f"{k['label']}: {k['value']} {k['unit']} ({k['change_pct']:+.1f}% vs previous period)")
    return "; ".join(parts) + "." if parts else ""


def peers_text(own: float | None, peers: float | None, n_peers: int) -> str:
    if own is None or peers is None:
        return ""
    rel = "tighter" if own < peers else "wider"
    return f"Average spread of {own:.1f} bps is {rel} than the median of {n_peers} industrial peers ({peers:.1f} bps)."


def report_headline(report: dict) -> str:
    kp = {k["label"]: k for k in report["sections"][0].get("kpis", [])}
    sp = next((v for k, v in kp.items() if k.startswith("Avg spread")), None)
    peer = report["sections"][1]["kpis"][0] if report["sections"][1].get("kpis") else None
    bits = []
    if sp and sp.get("change_pct") is not None:
        bits.append(f"Spreads {'tightened' if sp['change_pct'] < 0 else 'widened'} {abs(sp['change_pct']):.1f}% vs the previous period")
    if peer:
        bits.append(f"{abs(peer['value']):.1f} bps {'tighter' if peer['value'] < 0 else 'wider'} than peers")
    return (", ".join(bits) + ".") if bits else "Trading profile for the selected period."
