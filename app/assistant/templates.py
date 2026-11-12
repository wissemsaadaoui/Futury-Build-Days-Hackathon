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


# ---------------------------------------------------------------- Chat (repli sans LLM, app/assistant/chat.py)
def _ratio_word(r: float | None) -> str:
    return "n/a" if r is None else f"{r:.1f}x"


def chat_period(res: dict, latest: bool) -> str:
    """Résumé d'une période (get_period_summary) en 3 à 5 phrases, chiffres issus du résultat d'outil."""
    who, per = res["stock"]["name"], res["period"]
    when = f"In the latest week of data ({per['label']})" if latest and per["sessions"] <= 5 else f"Over {per['label']}"
    parts = []
    v, pr = res.get("volume_shares"), res.get("price")
    if v and pr:
        vs = f", {_ratio_word(v['ratio'])} its 20-day baseline," if v.get("ratio") is not None else ""
        parts.append(f"{when}, {who} traded {fmt.shares(v['period_avg'])} a day on average{vs} "
                     f"and the share price moved {pr['return_pct']:+.1f}%.")
    sp = res["spread_bps_25k_eur"]
    if sp.get("period_avg") is not None:
        lead = "The" if parts else f"{when}, the"
        before = f" versus {fmt.bps(sp['baseline_avg'])} before" if sp.get("baseline_avg") is not None else ""
        parts.append(f"{lead} average spread for a {fmt.eur(25_000)} trade was {fmt.bps(sp['period_avg'])}{before}"
                     + (f" ({sp['change_pct']:+.1f}%)." if sp.get("change_pct") is not None else "."))
    a = res.get("auction_share_pct")
    if a and a.get("period_avg") is not None:
        line = f"Auctions accounted for {a['period_avg']:.1f}% of volume" + (
            f" versus {a['baseline_avg']:.1f}% before." if a.get("baseline_avg") is not None else ".")
        tr = res.get("auction_share_trend_pct")
        if tr and per["sessions"] > 20 and tr["avg_20d_start"]["pct"] is not None and tr["avg_20d_end"]["pct"] is not None:
            pk = tr["peak_day"]
            line += (f" The 20-session average auction share of volume moved from {tr['avg_20d_start']['pct']:.1f}% to "
                     f"{tr['avg_20d_end']['pct']:.1f}%, with a peak of {pk['pct']:.1f}% on {_day(pk['date'])}.")
        parts.append(line)
    flagged = res.get("anomalies", []) + res.get("execution_alerts", [])
    if flagged:
        top = sorted(flagged, key=lambda x: (x["severity"] != "high", x["date"]))[0]
        n = res["n_anomalies"] + res["n_execution_alerts"]
        parts.append(f"{n} flag{'s' if n > 1 else ''} were raised; the most notable, on {_day(top['date'])}: "
                     f"{top['description'].rstrip('.')}.")
    else:
        parts.append("No anomaly or execution alert was flagged in this period.")
    if latest:
        parts.append(f"Latest data: {per['label']}.")
    return " ".join(parts[:5])


def chat_day_flags(res: dict) -> list[str]:
    """Phrase d'ouverture d'une question « pourquoi ce jour » : les anomalies/alertes signalées ce jour-là."""
    flags = res.get("anomalies", []) + res.get("execution_alerts", [])
    if not flags:
        return [f"No anomaly or execution alert was flagged on {_day(res['date'])}."]
    desc = "; ".join(f["description"].rstrip(".") for f in flags[:2])
    return [f"{_day(res['date'])} was flagged for: {desc}."]


def chat_peers(res: dict) -> str:
    who, per, own, med = res["stock"]["name"], res["period"], res["stock"], res["peer_median"]
    rk = res["spread_rank_tightest_first"]
    parts = [f"Over {per['label']}, {who}'s average spread for a {fmt.eur(25_000)} trade was "
             f"{fmt.bps(own['avg_spread_bps'])} versus a median of {fmt.bps(med['avg_spread_bps'])} across its "
             f"{res['n_peers']} peers (rank {rk['rank']} of {rk['of']}, tightest first)."]
    if own.get("return_pct") is not None and med.get("return_pct") is not None:
        parts.append(f"Its share price moved {own['return_pct']:+.1f}% versus a peer median of {med['return_pct']:+.1f}%.")
    if own.get("avg_turnover_eur") is not None and med.get("avg_turnover_eur") is not None:
        parts.append(f"Average daily turnover was {fmt.eur(own['avg_turnover_eur'])} versus a peer median of "
                     f"{fmt.eur(med['avg_turnover_eur'])}.")
    parts.append(f"Latest data: {per['label']}.")
    return " ".join(parts[:5])


def _day(d: str) -> str:
    import pandas as pd

    return pd.Timestamp(d).strftime("%-d %b %Y")


# ---------------------------------------------------------------- AI points (3–4 phrases courtes, repli sans LLM)
def impact_points(card: dict) -> list[str]:
    """Points courts de l'impact card, uniquement à partir des faits réels."""
    f = impact_facts(card)
    pts: list[str] = []
    if "volume" in f and "price" in f:
        pts.append(f"Volume was {_f(f['volume']['ratio_vs_baseline'])}x its usual level; the price moved "
                   f"{f['price']['change_pct']:+.1f}%." if f["price"].get("change_pct") is not None
                   else f"Volume was {_f(f['volume']['ratio_vs_baseline'])}x its usual level.")
    sp = f["spread_bps_25k_eur"]
    if sp.get("event_day") is not None and sp.get("baseline") is not None:
        chg = sp.get("change_pct")
        pts.append(f"Spread {fmt.bps(sp['event_day'])} versus {fmt.bps(sp['baseline'])} on average"
                   + (f" ({chg:+.1f}%)." if chg is not None else "."))
    it = f.get("intraday")
    if it and it.get("first_15min_volume_ratio_vs_same_time_20d") is not None:
        when = "after the publication" if it["announcement_during_session"] else "after the open"
        pts.append(f"First 15 minutes {when}: {_f(it['first_15min_volume_ratio_vs_same_time_20d'])}x the usual volume.")
    a = f.get("auction_share_pct")
    if a and a.get("event_day") is not None and a.get("baseline") is not None:
        pts.append(f"Auctions took {_f(a['event_day'])}% of volume versus {_f(a['baseline'])}% normally.")
    ex = f.get("peers", {}).get("excess_return_vs_peers_pct")
    if ex is not None and len(pts) < 4:
        pts.append(f"{_f(abs(ex))} percentage points {'better' if ex >= 0 else 'worse'} than the peer median.")
    return pts[:4]


def preview_points(preview: dict) -> list[str]:
    f = preview_facts(preview)
    n, label, et = f["past_events_n"], f["event_type"], preview["event_type"]
    if n == 0:
        return [f"No past {_noun(et, label, 2)} are available in the 2026 data."]
    pts = []
    sp, vr, stn = f.get("spread_change_pct"), f.get("volume_ratio"), f.get("sessions_to_normal")
    if sp:
        pts.append(f"{n} past {_noun(et, label, n)}: median spread change {sp['median']:+.1f}%"
                   + (f" ({sp['min']:+.1f}% to {sp['max']:+.1f}%)." if n > 1 else "."))
    if vr:
        pts.append(f"Median volume {vr['median']:.1f}x the usual level"
                   + (f" ({vr['min']:.1f}x to {vr['max']:.1f}x)." if n > 1 else "."))
    if stn:
        pts.append("The spread stayed within 10% of normal on the publication day." if stn["max"] == 0
                   else f"Liquidity back to normal within {_num(stn['max'])} session(s) at most.")
    if f.get("peer_events_n"):
        pts.append(f"{f['peer_events_n']} peer releases: median spread change {f['peers_spread_change_pct']['median']:+.1f}%.")
    return pts[:4]


def report_points(report: dict) -> list[str]:
    secs = {s["title"]: s for s in report["sections"]}
    kp = {k["label"]: k for k in secs.get("Trading profile", {}).get("kpis", [])}
    pts = []
    sp = next((v for k, v in kp.items() if k.startswith("Avg spread")), None)
    if sp and sp.get("value") is not None:
        chg = sp.get("change_pct")
        basis = "vs first half" if sp.get("change_basis") == "first_half" else "vs previous period"
        pts.append(f"Average spread {fmt.bps(sp['value'])}" + (f" ({chg:+.1f}% {basis})." if chg is not None else "."))
    vol = kp.get("Avg daily volume")
    if vol and vol.get("value") is not None:
        chg = vol.get("change_pct")
        pts.append(f"{fmt.shares(vol['value'])} traded a day on average" + (f" ({chg:+.1f}%)." if chg is not None else "."))
    peer = (secs.get("Peer comparison", {}).get("kpis") or [None])[0]
    if peer and peer.get("value") is not None:
        pts.append(f"{fmt.bps(abs(peer['value']))} {'tighter' if peer['value'] < 0 else 'wider'} than the peer median.")
    al = secs.get("Alerts")
    if al and al.get("kpis") is not None:
        n = sum(k["value"] or 0 for k in al["kpis"])
        pts.append(f"{fmt.count(n)} alert{'s' if n != 1 else ''} flagged in the period." if n else "No alert flagged in the period.")
    return pts[:4]
