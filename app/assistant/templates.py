"""Résumés de secours (sans LLM) : déterministes, toujours disponibles."""
from __future__ import annotations

from app.assistant import fmt
from app.assistant.facts import impact_facts, preview_facts


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
        s2 = (f"{subject} for a {fmt.eur(25_000)} trade {direction} to {fmt.bps(sp['event_day'])} "
              f"versus a 20-day average of {fmt.bps(sp['baseline'])} ({_f(sp.get('change_pct'))}%)")
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
        basis = "vs first half of the period" if k.get("change_basis") == "first_half" else "vs previous period"
        parts.append(f"{k['label']}: {fmt.value(k['value'], k['unit'])} ({k['change_pct']:+.1f}% {basis})")
    return "; ".join(parts) + "." if parts else ""


# Secteur (config.SECTORS) -> adjectif pour « … peers » ; secteur inconnu -> « peers » tout court
SECTOR_ADJECTIVE = {
    "Financials": "financial",
    "Technology": "technology",
    "Industrials": "industrial",
    "Consumer": "consumer",
    "Healthcare": "healthcare",
    "Utilities": "utility",
    "Real Estate": "real estate",
    "Materials": "materials",
    "Energy": "energy",
    "Telecommunications": "telecom",
}


def peers_label(sector: str | None) -> str:
    """'financial peers' pour Financials, 'peers' si le secteur est vide ou inconnu."""
    adj = SECTOR_ADJECTIVE.get((sector or "").strip())
    return f"{adj} peers" if adj else "peers"


def peers_text(own: float | None, peers: float | None, n_peers: int, sector: str | None = None) -> str:
    if own is None or peers is None:
        return ""
    rel = "tighter" if own < peers else "wider"
    return (f"Average spread of {fmt.bps(own)} is {rel} than the median of its {n_peers} {peers_label(sector)} "
            f"({fmt.bps(peers)}).")


def report_headline(report: dict) -> str:
    kp = {k["label"]: k for k in report["sections"][0].get("kpis", [])}
    sp = next((v for k, v in kp.items() if k.startswith("Avg spread")), None)
    peer = report["sections"][1]["kpis"][0] if report["sections"][1].get("kpis") else None
    bits = []
    if sp and sp.get("change_pct") is not None:
        basis = "the first half of the period" if sp.get("change_basis") == "first_half" else "the previous period"
        bits.append(f"Spreads {'tightened' if sp['change_pct'] < 0 else 'widened'} {abs(sp['change_pct']):.1f}% vs {basis}")
    if peer:
        bits.append(f"{fmt.bps(abs(peer['value']))} {'tighter' if peer['value'] < 0 else 'wider'} than peers")
    return (", ".join(bits) + ".") if bits else "Trading profile for the selected period."


# Pluriel « releases » par type d'événement (event preview)
PLURAL = {
    "ad_hoc": ("ad hoc announcement", "ad hoc announcements"),
    "agm": ("annual general meeting", "annual general meetings"),
    "voting_rights": ("voting rights notification", "voting rights notifications"),
    "directors_dealings": ("directors' dealings notification", "directors' dealings notifications"),
    "press_release": ("press release", "press releases"),
    "dividend": ("dividend announcement", "dividend announcements"),
    "m_and_a": ("M&A announcement", "M&A announcements"),
    "index_change": ("index change", "index changes"),
}


def _noun(event_type: str, label: str, n: int) -> str:
    one, many = PLURAL.get(event_type, (f"{label} release", f"{label} releases"))
    return one if n == 1 else many


def _num(x: float, nd: int = 1) -> str:
    return f"{x:.0f}" if float(x).is_integer() else f"{x:.{nd}f}"


def _rng(st: dict, unit: str = "", nd: int = 1) -> str:
    return f"{st['min']:.{nd}f}{unit} to {st['max']:.{nd}f}{unit}"


def preview_summary(preview: dict) -> str:
    """2 à 4 phrases sur les réactions PASSÉES du trading (aucune projection de prix)."""
    f = preview_facts(preview)
    n, label, et = f["past_events_n"], f["event_type"], preview["event_type"]
    who = f["company"]
    if n == 0:
        return (f"No past {_noun(et, label, 2)} are available in the 2026 data for {who}, "
                f"so there is no reference trading reaction to show.")
    sp, vr, stn = f.get("spread_change_pct"), f.get("volume_ratio"), f.get("sessions_to_normal")
    parts = []
    if n == 1:
        lead = f"In its only past {_noun(et, label, 1)} in the 2026 data, {who}'s"
        if sp:
            parts.append(f"{lead} spread on the publication day changed by {sp['median']:+.1f}% versus its 20-day average.")
        if vr:
            parts.append(f"Volume reached {vr['median']:.1f}x its usual level.")
    else:
        lead = f"In its past {n} {_noun(et, label, n)}, {who}'s"
        if sp:
            parts.append(f"{lead} spread on the publication day changed by a median of {sp['median']:+.1f}% "
                         f"({_rng(sp, '%')}) versus its 20-day average.")
        if vr:
            parts.append(f"Volume reached a median of {vr['median']:.1f}x its usual level ({_rng(vr, 'x')}).")
    if stn:
        if stn["max"] == 0:
            parts.append("The spread stayed within 10% of its normal level on the publication day.")
        else:
            parts.append(f"Liquidity was back to normal within {_num(stn['max'])} session(s) at most"
                         + (f" (median {_num(stn['median'])})." if n > 1 else "."))
    if f.get("peer_events_n"):
        p = f["peers_spread_change_pct"]
        parts.append(f"Across {f['peer_events_n']} peer releases, the median spread change was {p['median']:+.1f}%.")
    return " ".join(parts[:4])
