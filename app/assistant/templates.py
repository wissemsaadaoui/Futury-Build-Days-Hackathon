"""Résumés de secours (sans LLM) : déterministes, toujours disponibles."""
from __future__ import annotations

from app.assistant.facts import impact_facts


def ev_is_title(f: dict) -> bool:
    """True si l'événement est une vraie annonce (et pas un jour inhabituel sans annonce)."""
    return f.get("event_type") is not None


def _f(x: float | None, nd: int = 1) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def impact_summary(card: dict) -> str:
    """3 à 5 phrases : (1) volume, prix et peers, (2) spread, (3) réaction intraday, (4) enchères, (5) une alerte."""
    f = impact_facts(card)
    sp = f["spread_bps_25k_eur"]
    who = f["company"]
    lead = (f"On the day of the event ({f['event']}), {who}" if ev_is_title(f)
            else f"On {f.get('trading_day')}, an unusual trading day with no announcement, {who}")
    parts: list[str] = []

    if "volume" in f and "price" in f:
        s1 = f"{lead} traded {_f(f['volume']['ratio_vs_baseline'])}x its usual volume and the share price moved {_f(f['price']['change_pct'])}%"
        ex = f.get("peers", {}).get("excess_return_vs_peers_pct")
        if ex is not None:
            s1 += f", {_f(abs(ex))} percentage points {'better' if ex >= 0 else 'worse'} than the median of its peers"
        parts.append(s1 + ".")

    if sp.get("event_day") is not None and sp.get("baseline") is not None:
        chg = sp.get("change_pct") or 0
        direction = "widened" if chg > 0 else "tightened"
        subject = "The round-trip cost" if parts else f"{lead}'s round-trip cost"
        s2 = (f"{subject} for a 25,000 EUR trade {direction} to {_f(sp['event_day'])} bps "
              f"versus a 20-day average of {_f(sp['baseline'])} bps ({_f(sp.get('change_pct'))}%)")
        n = sp.get("sessions_until_back_to_normal")
        if chg > 10 and n is not None:  # « retour à la normale » n'a de sens qu'après un écartement
            s2 += f" and returned to normal after {n} session{'s' if n > 1 else ''}"
        parts.append(s2 + ".")

    it = f.get("intraday")
    if it and it.get("first_15min_volume_ratio_vs_same_time_20d") is not None:
        pc = it.get("price_change_pct") or {}
        when = "after the publication" if it["announcement_during_session"] else "after the open"
        moves = [f"{_f(pc[k])}% after {lbl}" for k, lbl in (("after_5min", "5 minutes"), ("after_30min", "30 minutes")) if pc.get(k) is not None]
        tail = f", and the price moved {' and '.join(moves)}" if moves else ""
        parts.append(
            f"In the first 15 minutes {when} ({it['reference'].split(' at ')[-1]}), volume was "
            f"{_f(it['first_15min_volume_ratio_vs_same_time_20d'])}x the usual level for that time of day{tail}."
        )

    auction_bits = []
    a = f.get("auction_share_pct")
    if a and a.get("event_day") is not None and a.get("baseline") is not None:
        auction_bits.append(f"auctions accounted for {_f(a['event_day'])}% of volume versus {_f(a['baseline'])}% normally")
    ca = (f.get("auctions") or {}).get("closing_auction_ratio_vs_baseline")
    if ca is not None:
        auction_bits.append(f"the closing auction was {_f(ca)}x its usual size")
    if auction_bits:
        s4 = "; ".join(auction_bits) + "."
        parts.append(s4[0].upper() + s4[1:])

    al = f.get("execution_alerts_that_day") or []
    if al:
        parts.append(f"Execution alert: {al[0]['description']}.")
    return " ".join(parts[:5])


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
    return f"Average spread of {own:.1f} bps is {rel} than the median of its {n_peers} peers ({peers:.1f} bps)."


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
