"""Chat libre de l'AI Assistant, ancré dans nos analyses (tool use Anthropic) – propriétaire : Alfred.

chat(isin, messages) -> {"answer", "links": [{"label", "type": day|event|preview|compare, "ref"}], "as_of"}

Flux : outils (wrappers des fonctions analytics, JSON compact, NaN -> null) -> LLM (max 4 tours d'outils)
-> garde-fou (chiffres présents dans les résultats d'outils + vocabulaire interdit) -> sinon réponse template
construite à partir du résultat de l'outil choisi par un routeur déterministe. Jamais d'exception vers l'API
(sauf ISIN inconnu -> NotFound -> 404).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app import config, etl
from app.analytics import data, metrics
from app.analytics._util import clean, iso, pct, r0, r1, r2, ratio
from app.analytics.impact import NotFound
from app.assistant import guard, llm, prompts, templates
from app.assistant.facts import EVENT_LABELS

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4
MAX_HISTORY = 6
MAX_TOKENS = 700
SIGNAL_TYPES = {"volume_spike", "spread_widening", "price_move"}
_WHO = re.compile(r"\b(investors?|institutional|retail)\b", re.I)

# ---------------------------------------------------------------- dates

def as_of() -> pd.Timestamp:
    """Dernière séance disponible dans les données (30.10.2026)."""
    return data.trading_days()[-1]


def today() -> pd.Timestamp:
    """Date réelle (Europe/Berlin) : peut être postérieure aux données."""
    return pd.Timestamp(datetime.now(ZoneInfo(config.TZ)).date())


def latest_sessions(n: int) -> pd.DatetimeIndex:
    return data.trading_days()[-n:]


def label_range(start: pd.Timestamp, end: pd.Timestamp) -> str:
    """'26–30 Oct 2026', '29 Sep – 30 Oct 2026', '30 Oct 2026'."""
    if start == end:
        return end.strftime("%-d %b %Y")
    if start.month == end.month and start.year == end.year:
        return f"{start.day}–{end.strftime('%-d %b %Y')}"
    return f"{start.strftime('%-d %b')} – {end.strftime('%-d %b %Y')}"


def context() -> dict:
    """Repères de dates passés au LLM ET inclus dans les faits du garde-fou."""
    days = data.trading_days()
    week = latest_sessions(5)
    month = days[(days.year == as_of().year) & (days.month == as_of().month)]
    return {
        "today": iso(today()),
        "latest_data_day": iso(as_of()),
        "latest_week": {"from": iso(week[0]), "to": iso(week[-1]), "label": label_range(week[0], week[-1])},
        "latest_month": {"from": iso(month[0]), "to": iso(month[-1]), "label": label_range(month[0], month[-1])},
        "first_data_day": iso(days[0]),
    }


def _range(start: str | None, end: str | None) -> pd.DatetimeIndex:
    days = data.trading_days()
    s = pd.Timestamp(start) if start else days[0]
    e = pd.Timestamp(end) if end else days[-1]
    return days[(days >= s) & (days <= e)]


# ---------------------------------------------------------------- outils

def _stock(isin: str) -> dict:
    return {k: v for k, v in data.stock_ref(isin).items() if k != "sector"}


def _anomalies(isin: str, start: pd.Timestamp, end: pd.Timestamp) -> tuple[list[dict], list[dict]]:
    from app.analytics.dashboard import _anomaly_rows  # import tardif (dashboard importe impact)

    px = data.ohlc(isin)
    vol = px["volume"].astype(float) if not px.empty else None
    rows = _anomaly_rows(isin, data.spread_series(isin), vol, start, end)
    compact = [{"date": r["date"], "type": r["type"], "severity": r["severity"], "description": r["description"]} for r in rows]
    return [a for a in compact if a["type"] in SIGNAL_TYPES], [a for a in compact if a["type"] not in SIGNAL_TYPES]


def tool_period_summary(isin: str, start: str | None = None, end: str | None = None) -> dict:
    rng = _range(start, end)
    if len(rng) == 0:
        return {"error": "No trading days in this period (data cover 2 Jan – 30 Oct 2026)."}
    days = data.trading_days()
    base = metrics.baseline_days(days, rng[0], config.BASELINE_DAYS)
    out: dict[str, Any] = {
        "stock": _stock(isin),
        "period": {"from": iso(rng[0]), "to": iso(rng[-1]), "label": label_range(rng[0], rng[-1]), "sessions": len(rng)},
        "baseline": f"{len(base)} trading days before the period",
    }
    sp = data.spread_series(isin)
    s_now, s_base = sp.reindex(rng).mean(), sp.reindex(base).mean()
    out["spread_bps_25k_eur"] = {"period_avg": r1(s_now), "baseline_avg": r1(s_base), "change_pct": r1(pct(s_now, s_base))}
    px = data.ohlc(isin)
    if not px.empty:
        vol, turn, close = px["volume"].astype(float), px["turnover_eur"].astype(float), px["close"].astype(float)
        v_now, v_base = vol.reindex(rng).mean(), vol.reindex(base).mean()
        out["volume_shares"] = {"period_avg": r0(v_now), "baseline_avg": r0(v_base), "ratio": r2(ratio(v_now, v_base))}
        t_now, t_base = turn.reindex(rng).mean(), turn.reindex(base).mean()
        out["turnover_eur"] = {"period_avg": r0(t_now), "baseline_avg": r0(t_base), "ratio": r2(ratio(t_now, t_base))}
        prev = close.reindex(days[days < rng[0]]).dropna()
        first = prev.iloc[-1] if len(prev) else close.reindex(rng).dropna().iloc[0]
        last = close.reindex(rng).dropna().iloc[-1]
        out["price"] = {"close_before_period": r2(first), "last_close": r2(last), "return_pct": r1(pct(last, first))}
    share = data.auction_share_series(isin)
    if not share.empty:
        a_now, a_base = share.reindex(rng).mean(), share.reindex(base).mean()
        out["auction_share_pct"] = {"period_avg": r1(a_now * 100), "baseline_avg": r1(a_base * 100),
                                    "change_pts": r1((a_now - a_base) * 100)}
    signals, alerts = _anomalies(isin, rng[0], rng[-1])
    out["anomalies"] = signals[:8]
    out["execution_alerts"] = alerts[:8]
    out["n_anomalies"], out["n_execution_alerts"] = len(signals), len(alerts)
    return out


def _pct100(x: float | None) -> float | None:
    return None if x is None else r1(x * 100)


def tool_day(isin: str, date: str) -> dict:
    from app.analytics import build_day_card
    from app.analytics.events import events_df

    day = pd.Timestamp(date).normalize()
    if day not in data.trading_days():
        return {"error": f"{iso(day)} is not a trading day in the data (2 Jan – 30 Oct 2026)."}
    ev = events_df(isin)
    linked = ev[pd.to_datetime(ev["trading_day"]) == day]
    if not linked.empty:
        from app.analytics import build_impact_card

        card = build_impact_card(linked.iloc[0]["event_id"], with_summary=False)
    else:
        card = build_day_card(isin, day)
    signals, alerts = _anomalies(isin, day, day)
    m = card["metrics"]
    it = card.get("intraday") or {}
    return {
        "date": iso(day),
        "stock": _stock(isin),
        "event": {k: card["event"][k] for k in ("event_id", "type", "title", "published_at")} if card.get("event") else None,
        "spread_bps_25k_eur": m["spread_bps"],
        "volume": m["volume"],
        "turnover_eur": m.get("turnover_eur"),
        "price": m["price"],
        "auction_share_pct": {"day": _pct100(m["auction_share"].get("event")),
                              "baseline": _pct100(m["auction_share"].get("baseline")),
                              "change_pts": _pct100(m["auction_share"].get("change_pts"))},
        "vs_peers": card["vs_peers"],
        "intraday": {"first_15min_ratio": (it.get("first_15min") or {}).get("ratio"),
                     "price_change_pct": it.get("price_change_pct")} if it else None,
        "anomalies": signals,
        "execution_alerts": alerts,
        "_card": card,  # retiré avant envoi au LLM ; sert au template
    }


def tool_list_events(isin: str) -> dict:
    from app.analytics import list_events

    evs = list_events(isin)["events"]
    upcoming = _upcoming_events(isin)
    return {
        "past_events": [{"event_id": e["event_id"], "date": e["trading_day"], "type": e["type"], "title": e["title"],
                         **e["headline_metric"]} for e in evs],
        "upcoming_events": upcoming,
    }


def _upcoming_events(isin: str) -> list[dict]:
    raw = etl.load_events()
    raw = raw[(raw["isin"] == isin) & (pd.to_datetime(raw["date"]) > as_of())]
    return [{"event_id": r["event_id"], "date": r["date"], "time": r["time"] or None, "type": r["type"], "title": r["title"]}
            for _, r in raw.sort_values("date").iterrows()]


def tool_impact_card(isin: str, event_id: str) -> dict:
    from app.analytics import build_impact_card

    card = build_impact_card(event_id, with_summary=False)
    m = card["metrics"]
    return {
        "event": card["event"],
        "spread_bps_25k_eur": m["spread_bps"], "volume": m["volume"], "price": m["price"],
        "auction_share": m["auction_share"], "vs_peers": card["vs_peers"],
        "intraday": {"first_15min_ratio": (card.get("intraday") or {}).get("first_15min", {}).get("ratio"),
                     "price_change_pct": (card.get("intraday") or {}).get("price_change_pct")},
        "_card": card,
    }


def tool_event_preview(isin: str, event_type: str, date: str | None = None) -> dict:
    from app.analytics import build_event_preview

    p = build_event_preview(isin, event_type, date)
    strip = lambda h: {k: v for k, v in h.items() if k != "events"}  # noqa: E731
    return {
        "event_type": p["event_type"], "upcoming": p["upcoming"], "as_of": p["as_of"],
        "own_history": strip(p["own_history"]), "past_events": p["own_history"]["events"],
        "peers": strip(p["peers"]), "attention_points": p["attention_points"],
        "confidence": p["confidence"], "note": p["note"],
        "_preview": p,
    }


def tool_peer_comparison(isin: str, start: str | None = None, end: str | None = None) -> dict:
    rng = _range(start, end)
    if len(rng) == 0:
        return {"error": "No trading days in this period (data cover 2 Jan – 30 Oct 2026)."}
    days = data.trading_days()

    def row(i: str) -> dict:
        sp = data.spread_series(i).reindex(rng)
        px = data.ohlc(i)
        ret = turn = None
        if not px.empty:
            close = px["close"].astype(float)
            prev = close.reindex(days[days < rng[0]]).dropna()
            inside = close.reindex(rng).dropna()
            if len(inside):
                first = prev.iloc[-1] if len(prev) else inside.iloc[0]
                ret = r1(pct(inside.iloc[-1], first))
            turn = r0(px["turnover_eur"].astype(float).reindex(rng).mean())
        return {"isin": i, "name": data.name_of(i), "avg_spread_bps": r1(sp.mean()), "return_pct": ret,
                "avg_turnover_eur": turn, "spread_sessions": int(sp.notna().sum())}

    own = row(isin)
    peers = [row(p) for p in data.peers_of(isin)]
    peers = [p for p in peers if p["spread_sessions"] > 0]
    med = lambda k: r1(np.nanmedian([p[k] for p in peers if p[k] is not None])) if any(p[k] is not None for p in peers) else None  # noqa: E731
    ranked = sorted([own, *peers], key=lambda p: (p["avg_spread_bps"] is None, p["avg_spread_bps"] or 0))
    return {
        "period": {"from": iso(rng[0]), "to": iso(rng[-1]), "label": label_range(rng[0], rng[-1])},
        "stock": own,
        "peers": peers,
        "peer_median": {"avg_spread_bps": med("avg_spread_bps"), "return_pct": med("return_pct"),
                        "avg_turnover_eur": r0(np.nanmedian([p["avg_turnover_eur"] for p in peers if p["avg_turnover_eur"]]))
                        if any(p["avg_turnover_eur"] for p in peers) else None},
        "spread_rank_tightest_first": {"rank": ranked.index(own) + 1, "of": len(ranked)},
        "n_peers": len(peers),
    }


TOOLS: list[dict] = [
    {
        "name": "get_period_summary",
        "description": "Trading summary of the stock over a period vs the 20 trading days before it: volume, turnover, "
                       "XLM spread (EUR 25,000), return, auction share, anomalies and execution alerts. "
                       "Dates YYYY-MM-DD within 2026-01-02..2026-10-30.",
        "input_schema": {"type": "object", "properties": {"from": {"type": "string"}, "to": {"type": "string"}},
                         "required": ["from", "to"]},
    },
    {
        "name": "get_day",
        "description": "Full analysis of one trading day (spread, volume, price, peers, auctions, intraday, anomalies, "
                       "alerts, linked announcement). Date YYYY-MM-DD.",
        "input_schema": {"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]},
    },
    {
        "name": "list_events",
        "description": "Company announcements: past events with their headline trading metrics, and upcoming events.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_impact_card",
        "description": "Trading reaction to one past announcement (event_id from list_events).",
        "input_schema": {"type": "object", "properties": {"event_id": {"type": "string"}}, "required": ["event_id"]},
    },
    {
        "name": "get_event_preview",
        "description": "How trading reacted to PAST announcements of a type (spread, volume, sessions to normal, absolute "
                       "price move): statistics only, never a projection. event_type e.g. quarterly_results; date = "
                       "upcoming event date (only events before it are used).",
        "input_schema": {"type": "object",
                         "properties": {"event_type": {"type": "string"}, "date": {"type": "string"}},
                         "required": ["event_type"]},
    },
    {
        "name": "get_peer_comparison",
        "description": "The stock vs its peers over a period: average spread, return, turnover, spread rank.",
        "input_schema": {"type": "object", "properties": {"from": {"type": "string"}, "to": {"type": "string"}},
                         "required": ["from", "to"]},
    },
]


def run_tool(isin: str, name: str, args: dict) -> dict:
    """Exécute un outil ; toute erreur devient {"error": ...} (le LLM peut alors corriger sa requête)."""
    fns: dict[str, Callable[..., dict]] = {
        "get_period_summary": lambda a: tool_period_summary(isin, a.get("from"), a.get("to")),
        "get_day": lambda a: tool_day(isin, a["date"]),
        "list_events": lambda a: tool_list_events(isin),
        "get_impact_card": lambda a: tool_impact_card(isin, a["event_id"]),
        "get_event_preview": lambda a: tool_event_preview(isin, a["event_type"], a.get("date")),
        "get_peer_comparison": lambda a: tool_peer_comparison(isin, a.get("from"), a.get("to")),
    }
    if name not in fns:
        return {"error": f"Unknown tool {name}"}
    try:
        return clean(fns[name](args or {}))
    except (NotFound, KeyError, ValueError) as exc:
        return {"error": str(exc.args[0] if exc.args else exc)}
    except Exception as exc:  # jamais d'erreur 500 à cause d'un outil
        log.warning("chat tool %s failed: %s", name, exc)
        return {"error": "This analysis is not available."}


def public(result: dict) -> dict:
    """Résultat d'outil sans les objets internes (préfixe _), tel qu'envoyé au LLM."""
    return {k: v for k, v in result.items() if not k.startswith("_")}


# ---------------------------------------------------------------- liens

def links_for(calls: list[tuple[str, dict, dict]]) -> list[dict]:
    out: list[dict] = []

    def add(label: str, type_: str, ref: str) -> None:
        if not any(l["type"] == type_ and l["ref"] == ref for l in out):
            out.append({"label": label, "type": type_, "ref": ref})

    for name, args, res in calls:
        if res.get("error"):
            continue
        if name == "get_day":
            ev = res.get("event")
            if ev:
                add(f"Impact card: {ev['title'][:40]}", "event", ev["event_id"])
            else:
                add(f"Day view {fmt_day(res['date'])}", "day", res["date"])
        elif name == "get_impact_card":
            add(f"Impact card: {res['event']['title'][:40]}", "event", res["event"]["event_id"])
        elif name == "get_event_preview":
            add("What to expect", "preview", res["event_type"])
        elif name == "get_peer_comparison":
            add("Compare announcements", "compare", "")
        elif name == "get_period_summary":
            flagged = sorted({a["date"] for a in res.get("anomalies", []) + res.get("execution_alerts", [])
                              if a["severity"] == "high"}, reverse=True)
            for d in flagged[:2]:
                add(f"Day view {fmt_day(d)}", "day", d)
    return out[:4]


def fmt_day(d: str) -> str:
    return pd.Timestamp(d).strftime("%-d %b %Y")


# ---------------------------------------------------------------- routeur + templates (sans LLM)

_OUT_OF_SCOPE = re.compile(
    r"\b(will|going to|forecast\w*|predict\w*|target|tomorrow|next (week|month|year)|should (i|we)|buy|sell|hold|"
    r"recommend\w*|worth (buying|it)|news|rumou?r|why did .* (ceo|management)|dividend yield)\b",
    re.I,
)
_MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def parse_date(text: str) -> str | None:
    """'2026-09-29', '29 Sep', '29 September 2026', 'Sep 29' -> 'YYYY-MM-DD' (année des données par défaut)."""
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", text)
    if m:
        return m.group(0)
    year = as_of().year
    m = re.search(r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\.?\s+([A-Za-z]{3})[a-z]*\.?(?:\s+(20\d\d))?\b", text)
    if m and m.group(2).lower() in _MONTHS:
        return f"{int(m.group(3) or year)}-{_MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"\b([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", text)
    if m and m.group(1).lower() in _MONTHS:
        return f"{year}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return None


def route(isin: str, question: str) -> tuple[str, dict] | None:
    """Outil le plus pertinent pour la question (None = hors périmètre)."""
    q = question.lower()
    ctx = context()
    if _OUT_OF_SCOPE.search(q) and not re.search(r"\b(react|reaction|past|historical|expect)\b", q):
        return None
    day = parse_date(question)
    if day:
        return "get_day", {"date": day}
    if re.search(r"\b(expect|upcoming|q[1-4]|results?|release|earnings|quarterly|annual|publication)\b", q):
        etype = "annual_results" if "annual" in q or "full year" in q or "fy" in q.split() else "quarterly_results"
        if "ad hoc" in q or "ad-hoc" in q:
            etype = "ad_hoc"
        up = next((e for e in _upcoming_events(isin) if e["type"] == etype), None)
        return "get_event_preview", {"event_type": etype, "date": up["date"] if up else None}
    if re.search(r"\b(peers?|compare|comparison|competitors?|sector|vs)\b", q):
        m = ctx["latest_month"]
        return "get_peer_comparison", {"from": m["from"], "to": m["to"]}
    if re.search(r"\b(month)\b", q):
        m = ctx["latest_month"]
        return "get_period_summary", {"from": m["from"], "to": m["to"]}
    if re.search(r"\b(year|ytd|2026)\b", q):
        return "get_period_summary", {"from": ctx["first_data_day"], "to": ctx["latest_data_day"]}
    if re.search(r"\b(today|yesterday|latest day|last day)\b", q):
        return "get_day", {"date": ctx["latest_data_day"]}
    w = ctx["latest_week"]
    return "get_period_summary", {"from": w["from"], "to": w["to"]}


REFUSAL = (
    "This assistant only describes past Xetra trading in this tool, so it cannot say where the share price is heading, "
    "give trading advice or comment on external news. "
    "You could ask instead: \"How did liquidity react to past quarterly results?\" or \"What happened in the latest week?\""
)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"(])", text.strip()) if s]


def template_answer(name: str, res: dict, ctx: dict) -> str:
    """Réponse sans LLM, uniquement à partir du résultat de l'outil (3 à 5 phrases)."""
    if res.get("error"):
        return f"{res['error']} Latest data: {ctx['latest_week']['label']}. Try a date between 2 Jan and 30 Oct 2026."
    if name == "get_period_summary":
        return templates.chat_period(res, latest=res["period"]["to"] == ctx["latest_data_day"])
    if name in ("get_day", "get_impact_card"):
        card = res["_card"]
        lead = templates.chat_day_flags(res) if name == "get_day" else []
        body = _sentences(templates.impact_summary(card))
        return " ".join((lead + body)[:5])
    if name == "get_event_preview":
        p = res["_preview"]
        parts = _sentences(templates.preview_summary(p))
        up = p.get("upcoming")
        if up and up.get("date"):
            noun = templates._noun(p["event_type"], EVENT_LABELS.get(p["event_type"], p["event_type"]), 1)
            parts.insert(0, f"The next {noun} is on {fmt_day(up['date'])}; market data in this tool end on "
                            f"{fmt_day(ctx['latest_data_day'])}, so only past releases can be described.")
        if p.get("confidence") == "low":
            parts.append(f"These figures rest on only {p['own_history']['n']} past release(s), so they are a thin basis.")
        return " ".join(parts[:5])
    if name == "get_peer_comparison":
        return templates.chat_peers(res)
    if name == "list_events":
        past = res["past_events"]
        return (f"The event calendar has {len(past)} past announcements with trading data. "
                + (f"The next scheduled one is {res['upcoming_events'][0]['title']} on "
                   f"{fmt_day(res['upcoming_events'][0]['date'])}." if res["upcoming_events"] else ""))
    return "No analysis is available for this question."


# ---------------------------------------------------------------- LLM (tool use)

def _client():
    import anthropic

    return anthropic.Anthropic(api_key=config.LLM_API_KEY, timeout=config.LLM_TIMEOUT_S)


def _history(messages: list[dict]) -> list[dict]:
    msgs = [{"role": m["role"], "content": str(m["content"])[:2000]} for m in messages
            if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()][-MAX_HISTORY:]
    while msgs and msgs[0]["role"] != "user":  # l'API Anthropic exige un premier message utilisateur
        msgs.pop(0)
    return msgs


def answer_ok(text: str | None, facts: dict) -> bool:
    return bool(text) and guard.check(text, facts) and not _WHO.search(text or "")


def _llm_answer(isin: str, messages: list[dict], ctx: dict) -> tuple[str | None, list[tuple[str, dict, dict]]]:
    """(texte, appels d'outils). Texte None si LLM indisponible, trop de tours ou erreur."""
    if not (llm.is_configured() and config.LLM_PROVIDER == "anthropic"):
        return None, []
    calls: list[tuple[str, dict, dict]] = []
    system = prompts.CHAT_SYSTEM.format(company=data.name_of(isin), isin=isin, **_ctx_flat(ctx))
    convo: list[dict] = list(messages)
    try:
        client = _client()
        model = config.LLM_MODEL or llm.DEFAULT_MODELS["anthropic"]
        for round_ in range(MAX_TOOL_ROUNDS + 1):
            resp = client.messages.create(
                model=model, max_tokens=MAX_TOKENS, thinking={"type": "disabled"},
                system=system, tools=TOOLS, messages=convo,
            )
            uses = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
            if resp.stop_reason != "tool_use" or not uses:
                text = " ".join("".join(b.text for b in resp.content if getattr(b, "type", "") == "text").split())
                return (text or None), calls
            if round_ == MAX_TOOL_ROUNDS:
                return None, calls  # trop de tours d'outils
            convo.append({"role": "assistant", "content": resp.content})
            results = []
            for b in uses:
                res = run_tool(isin, b.name, dict(b.input or {}))
                calls.append((b.name, dict(b.input or {}), res))
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": json.dumps(public(res), ensure_ascii=False)})
            convo.append({"role": "user", "content": results})
    except Exception as exc:  # réseau, quota, clé invalide…
        log.warning("chat LLM failed: %s", exc)
    return None, calls


def _ctx_flat(ctx: dict) -> dict:
    return {
        "today": ctx["today"], "as_of": ctx["latest_data_day"],
        "latest_week": f"{ctx['latest_week']['label']} ({ctx['latest_week']['from']} to {ctx['latest_week']['to']})",
        "latest_month": f"{ctx['latest_month']['label']} ({ctx['latest_month']['from']} to {ctx['latest_month']['to']})",
    }


# ---------------------------------------------------------------- point d'entrée

def chat(isin: str, messages: list[dict]) -> dict:
    if not data.known_isin(isin):
        raise NotFound(f"Unknown ISIN {isin}")
    ctx = context()
    msgs = _history(messages)
    question = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
    out = {"answer": "", "links": [], "as_of": ctx["latest_data_day"]}
    if not question:
        out["answer"] = "Ask a question about pbb's trading, for example \"What happened in the latest week?\""
        return out

    text, calls = _llm_answer(isin, msgs, ctx)
    facts = {"context": ctx, "tool_results": [public(r) for _, _, r in calls]}
    if text and calls and answer_ok(text, facts):
        out["answer"], out["links"] = text, links_for(calls)
        return out
    if text and not calls and answer_ok(text, {"context": ctx}) and not re.search(r"\d", text.replace("2026", "")):
        out["answer"] = text  # refus / redirection sans chiffres : acceptée telle quelle
        return out

    # Repli déterministe : routeur -> outil -> template
    picked = route(isin, question)
    if picked is None:
        out["answer"] = REFUSAL
        return out
    name, args = picked
    res = run_tool(isin, name, args)
    out["answer"] = template_answer(name, res, ctx)
    out["links"] = links_for([(name, args, res)])
    return out
