"""Mise en page PDF (reportlab) des sorties de app.analytics : aucun calcul, uniquement de la présentation."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, KeepInFrame, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DISCLAIMER = "Descriptive analysis of historical Xetra trading data. Not investment advice."

PAGE_W, PAGE_H = A4
MARGIN = 14 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#616e7c")
ACCENT = colors.HexColor("#0b5cad")
RULE = colors.HexColor("#d9dee4")
TILE_BG = colors.HexColor("#f2f5f8")
UP = colors.HexColor("#1b7f3b")
DOWN = colors.HexColor("#b42318")
DEMO = colors.HexColor("#9a6700")

_base = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("title", parent=_base["Title"], fontSize=16, leading=19, alignment=0, textColor=INK, spaceAfter=1 * mm),
    "sub": ParagraphStyle("sub", parent=_base["Normal"], fontSize=8.5, leading=11, textColor=MUTED),
    "h2": ParagraphStyle("h2", parent=_base["Heading2"], fontSize=10.5, leading=13, textColor=ACCENT, spaceBefore=3 * mm, spaceAfter=1.5 * mm),
    "body": ParagraphStyle("body", parent=_base["Normal"], fontSize=9, leading=12.5, textColor=INK),
    "small": ParagraphStyle("small", parent=_base["Normal"], fontSize=7.5, leading=9.5, textColor=MUTED),
    "cell": ParagraphStyle("cell", parent=_base["Normal"], fontSize=7.8, leading=9.5, textColor=INK),
    "tile_label": ParagraphStyle("tile_label", parent=_base["Normal"], fontSize=7.5, leading=9, textColor=MUTED, alignment=TA_CENTER),
    "tile_value": ParagraphStyle("tile_value", parent=_base["Normal"], fontSize=14, leading=17, textColor=INK, alignment=TA_CENTER, fontName="Helvetica-Bold"),
    "tile_note": ParagraphStyle("tile_note", parent=_base["Normal"], fontSize=7.5, leading=9, textColor=MUTED, alignment=TA_CENTER),
    "demo": ParagraphStyle("demo", parent=_base["Normal"], fontSize=7.5, leading=9.5, textColor=DEMO),
}


# ---------- formatage (None -> « – », jamais de NaN) ----------
def _esc(text: Any) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def num(x: Any, decimals: int = 0, suffix: str = "") -> str:
    if x is None:
        return "–"
    return f"{x:,.{decimals}f}{suffix}"


def signed(x: Any, decimals: int = 1, suffix: str = "%") -> str:
    if x is None:
        return "–"
    return f"{x:+,.{decimals}f}{suffix}"


def ratio(x: Any) -> str:
    return "–" if x is None else f"{x:,.2f}×"


def share(x: Any) -> str:
    """Ratio 0–1 -> pourcentage."""
    return "–" if x is None else f"{x * 100:.1f}%"


def _color(x: Any) -> colors.Color:
    if x is None or x == 0:
        return INK
    return UP if x > 0 else DOWN


# ---------- blocs communs ----------
def _header(title: str, subtitle: str) -> list[Flowable]:
    return [Paragraph(_esc(title), S["title"]), Paragraph(subtitle, S["sub"]), Spacer(1, 2 * mm), _rule()]


def _rule() -> Table:
    t = Table([[""]], colWidths=[CONTENT_W], rowHeights=[0.6])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.6, RULE)]))
    return t


def _tiles(tiles: list[tuple[str, str, str, colors.Color]]) -> Table:
    """Tuiles de chiffres clés : (libellé, valeur, note, couleur de la valeur)."""
    cells = []
    for label, value, note, color in tiles:
        style = ParagraphStyle("v", parent=S["tile_value"], textColor=color)
        cells.append([Paragraph(_esc(label), S["tile_label"]), Paragraph(_esc(value), style), Paragraph(_esc(note), S["tile_note"])])
    gap = 2.5 * mm
    w = (CONTENT_W - gap * (len(tiles) - 1)) / len(tiles)
    row, widths = [], []
    for i, c in enumerate(cells):
        inner = Table([[x] for x in c], colWidths=[w])
        inner.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), TILE_BG),
                    ("TOPPADDING", (0, 0), (-1, 0), 2.5 * mm),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 2.5 * mm),
                    ("TOPPADDING", (0, 1), (-1, -1), 0.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -2), 0.5),
                ]
            )
        )
        row.append(inner)
        widths.append(w)
        if i < len(cells) - 1:
            row.append("")
            widths.append(gap)
    t = Table([row], colWidths=widths)
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def _table(header: list[str], rows: list[list[Any]], col_widths: list[float], align_right_from: int = 1) -> Table:
    data = [[Paragraph(f"<b>{_esc(h)}</b>", S["cell"]) for h in header]]
    for r in rows:
        data.append([c if isinstance(c, Flowable) else Paragraph(_esc(c), S["cell"]) for c in r])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]
    t.setStyle(TableStyle(style))
    for row in data:
        for c in row[align_right_from:]:
            c.style = ParagraphStyle("r", parent=c.style, alignment=2)
    return t


def _demo_note(status: dict[str, str] | None) -> list[Flowable]:
    """Signale les parties encore en données de démo (_data_status != "real")."""
    demo = sorted(k.replace("_", " ") for k, v in (status or {}).items() if v != "real")
    if not demo:
        return []
    return [Paragraph(f"<b>Demo data:</b> {_esc(', '.join(demo))} – placeholder values, not real market data.", S["demo"])]


def _footer(generated_at: str | None, disclaimer: str = DISCLAIMER):
    def draw(canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.line(MARGIN, 11 * mm, PAGE_W - MARGIN, 11 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 7.5 * mm, disclaimer)
        right = "Issuer Intelligence Hub" + (f" · generated {generated_at[:16].replace('T', ' ')}" if generated_at else "")
        canvas.drawRightString(PAGE_W - MARGIN, 7.5 * mm, right)
        canvas.restoreState()

    return draw


def _build(story: list[Flowable], title: str, generated_at: str | None, disclaimer: str = DISCLAIMER, one_page: bool = False) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=16 * mm,
        title=title,
        author="Issuer Intelligence Hub",
    )
    if one_page:
        story = [KeepInFrame(doc.width, doc.height, story, mode="shrink")]
    footer = _footer(generated_at, disclaimer)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def _stock_line(stock: dict) -> str:
    parts = [stock.get("isin"), stock.get("index"), stock.get("sector")]
    return " · ".join(_esc(p) for p in parts if p)


# ---------- impact card ----------
def _two_columns(left: Flowable, right: Flowable, left_share: float = 0.5) -> Table:
    gap = CONTENT_W * 0.04
    lw = (CONTENT_W - gap) * left_share
    t = Table([[left, "", right]], colWidths=[lw, gap, CONTENT_W - gap - lw])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _intraday_chart(intraday: dict) -> Drawing:
    """Prix (VWAP par minute) et volume par minute, ligne verticale à la minute de référence (offset 0)."""
    w, h = CONTENT_W, 42 * mm
    left, right, bottom, top = 12 * mm, 3 * mm, 6 * mm, 6 * mm
    vol_h = 9 * mm
    d = Drawing(w, h)
    minutes = intraday["minutes"]
    if not minutes:
        return d
    x0, x1 = minutes[0]["offset_min"], minutes[-1]["offset_min"]
    plot_w = w - left - right

    def x(offset: int) -> float:
        return left + (offset - x0) / max(x1 - x0, 1) * plot_w

    # Volume (barres en bas)
    vmax = max((m.get("volume") or 0) for m in minutes) or 1
    bar_w = max(plot_w / len(minutes) * 0.8, 0.4)
    for m in minutes:
        v = m.get("volume") or 0
        if v:
            d.add(Rect(x(m["offset_min"]) - bar_w / 2, bottom, bar_w, v / vmax * vol_h, fillColor=colors.HexColor("#9fb3c8"), strokeColor=None))
    # Prix (VWAP), segments interrompus là où il n'y a pas d'exécution
    prices = [m["vwap"] for m in minutes if m.get("vwap") is not None]
    if prices:
        lo, hi = min(prices), max(prices)
        span = (hi - lo) or abs(hi) * 0.01 or 1
        p_bottom, p_top = bottom + vol_h + 3 * mm, h - top

        def y(price: float) -> float:
            return p_bottom + (price - lo) / span * (p_top - p_bottom)

        # Titre peu liquide : beaucoup de minutes sans exécution -> on relie les minutes qui en ont une
        pts = [(x(m["offset_min"]), y(m["vwap"])) for m in minutes if m.get("vwap") is not None]
        if len(pts) >= 2:
            d.add(PolyLine([c for pt in pts for c in pt], strokeColor=INK, strokeWidth=1))
        for px, py in pts:
            d.add(Circle(px, py, 0.6, fillColor=INK, strokeColor=None))
        d.add(String(left - 1.5 * mm, p_top - 2, f"{hi:.2f}", fontSize=6.5, fillColor=MUTED, textAnchor="end"))
        d.add(String(left - 1.5 * mm, p_bottom, f"{lo:.2f}", fontSize=6.5, fillColor=MUTED, textAnchor="end"))
    # Minute de référence
    if x0 <= 0 <= x1:
        d.add(Line(x(0), bottom, x(0), h - top, strokeColor=ACCENT, strokeWidth=0.8, strokeDashArray=[2, 2]))
        d.add(String(x(0) + 1.5, h - top + 1, "announcement" if intraday.get("during_session") else "open", fontSize=6.5, fillColor=ACCENT))
    for off in range(x0 - x0 % 30, x1 + 1, 30):
        if off >= x0:
            d.add(String(x(off), 0.5 * mm, f"{off:+d} min" if off else "0", fontSize=6, fillColor=MUTED, textAnchor="middle"))
    d.add(String(left, h - 3, "Price (VWAP per minute, EUR) and volume per minute", fontSize=7, fillColor=MUTED))
    return d


def _intraday_block(intraday: dict) -> list[Flowable]:
    f15, pc = intraday["first_15min"], intraday["price_change_pct"]
    ref = intraday["reference_time"][:16].replace("T", " ")
    where = "from the announcement" if intraday.get("during_session") else "from the market open (announcement outside trading hours or unknown time)"
    return [
        Paragraph(f"Intraday reaction <font size=8 color='#616e7c'>({_esc(where)}, {_esc(ref)})</font>", S["h2"]),
        _tiles(
            [
                ("First 15 min volume", ratio(f15.get("ratio")), f"{num(f15.get('volume'))} vs {num(f15.get('baseline'))} shares", INK),
                ("Price after 5 min", signed(pc.get("after_5min")), "", _color(pc.get("after_5min"))),
                ("Price after 30 min", signed(pc.get("after_30min")), "", _color(pc.get("after_30min"))),
                ("Price after 60 min", signed(pc.get("after_60min")), "", _color(pc.get("after_60min"))),
            ]
        ),
        Spacer(1, 1.5 * mm),
        _intraday_chart(intraday),
    ]


def _pre_disclosure_block(pre: dict) -> list[Flowable]:
    w = pre["window"]
    rows = [
        [d["date"], ", ".join(t.replace("_", " ") for t in d.get("anomaly_types") or []) or "–", ratio(d.get("volume_ratio")), signed(d.get("agent_net_flow_eur"), 0, " EUR")]
        for d in pre["days"]
    ]
    out: list[Flowable] = [
        Paragraph(f"Before the disclosure <font size=8 color='#616e7c'>({w['sessions']} sessions, {_esc(w['from'])} to {_esc(w['to'])})</font>", S["h2"]),
        Paragraph(_esc(pre.get("summary") or ""), S["body"]),
    ]
    if rows:
        out += [Spacer(1, 1 * mm), _table(["Date", "Flagged activity", "Volume vs baseline", "Agent net flow"], rows, [CONTENT_W * x for x in (0.14, 0.52, 0.16, 0.18)], align_right_from=2)]
    return out


def impact_card_pdf(card: dict) -> bytes:
    stock, ev, m = card["stock"], card.get("event"), card["metrics"]
    if ev:
        title = f"{stock['name']} – {ev['title']}"
        when = (ev.get("published_at") or ev["trading_day"])[:16].replace("T", " ")
        sub = f"{_stock_line(stock)}<br/>{_esc(ev['type'].replace('_', ' ').capitalize())} · published {_esc(when)} · measured on trading day {_esc(ev['trading_day'])}"
        if ev.get("source_url"):
            sub += f' · <link href="{_esc(ev["source_url"])}" color="#0b5cad">source</link>'
    else:
        day = next((p["date"] for p in card.get("window", []) if p["offset"] == 0), "")
        title = f"{stock['name']} – notable trading day {day}"
        sub = f"{_stock_line(stock)}<br/>Unusual trading day with no announcement on record"
    b = card["baseline"]
    sub += f"<br/>Baseline: {_esc(b['method'])} ({_esc(b['from'])} to {_esc(b['to'])})"

    vol, price, spread, vp = m["volume"], m["price"], m["spread_bps"], card["vs_peers"]
    story: list[Flowable] = _header(title, sub)
    story += [
        Spacer(1, 3 * mm),
        _tiles(
            [
                ("Volume vs baseline", ratio(vol.get("ratio")), f"{num(vol.get('event'))} shares", INK),
                ("Price change", signed(price.get("change_pct")), f"close {num(price.get('close'), 2)} EUR", _color(price.get("change_pct"))),
                ("Spread change (25k EUR)", signed(spread.get("change_pct")), f"{num(spread.get('event'), 1)} vs {num(spread.get('baseline'), 1)} bps", INK),
                ("Return vs peers", signed(vp.get("excess_return_pct"), 1, " pts"), f"peer median {signed(vp.get('peer_avg_price_change_pct'))}", _color(vp.get("excess_return_pct"))),
            ]
        ),
        Paragraph("Summary", S["h2"]),
        Paragraph(_esc(card.get("ai_summary") or "–"), S["body"]),
    ]
    if card.get("intraday"):
        story += _intraday_block(card["intraday"])

    oa, ca = m["opening_auction"], m["closing_auction"]
    auctions = _table(
        ["Auction (shares)", "Volume", "Usual", "Ratio"],
        [
            ["Opening auction", num(oa.get("volume")), num(oa.get("baseline")), ratio(oa.get("ratio"))],
            ["Closing auction", num(ca.get("volume")), num(ca.get("baseline")), ratio(ca.get("ratio"))],
        ],
        [CONTENT_W * 0.48 * x for x in (0.4, 0.2, 0.2, 0.2)],
    )
    flows = _table(
        ["Net order flow (shares)", "Bought", "Sold", "Net"],
        [[p["type"].replace("_", " ").title(), num(p.get("buy")), num(p.get("sell")), signed(p.get("net"), 0, "")] for p in card["flows"]["by_participant"]],
        [CONTENT_W * 0.48 * x for x in (0.37, 0.21, 0.21, 0.21)],
    )
    story += [Paragraph("Auctions and order flow", S["h2"]), _two_columns(auctions, flows)]

    lvl = (card.get("technical_context") or {}).get("broke_level")
    if lvl:
        story += [Spacer(1, 2 * mm), Paragraph(f"<b>Price level crossed:</b> the close moved through the {_esc(lvl['type'])} at {num(lvl['price'], 2)} EUR (descriptive only).", S["body"])]
    if card.get("pre_disclosure_activity"):
        story += _pre_disclosure_block(card["pre_disclosure_activity"])

    story += [Spacer(1, 2 * mm), *_demo_note(card.get("_data_status"))]
    return _build(story, title, card.get("generated_at"), one_page=True)


# ---------- IR snapshot ----------
_UNIT_FMT = {
    "shares": lambda v: num(v),
    "EUR": lambda v: num(v, 0, " EUR"),
    "bps": lambda v: num(v, 1, " bps"),
    "ratio": lambda v: share(v),
    "pct": lambda v: num(v, 1, "%"),
}
_TREND = {"up": "up", "down": "down", "flat": "flat", "better": "better", "worse": "worse"}


def report_pdf(report: dict) -> bytes:
    stock, period = report["stock"], report["period"]
    title = f"{stock['name']} – IR trading snapshot"
    sub = f"{_stock_line(stock)}<br/>Period {_esc(period['from'])} to {_esc(period['to'])}"
    story: list[Flowable] = _header(title, sub)
    story += [Spacer(1, 2 * mm), Paragraph(f"<b>{_esc(report.get('headline') or '')}</b>", S["body"])]

    for sec in report["sections"]:
        story.append(Paragraph(_esc(sec["title"]), S["h2"]))
        kpis = sec.get("kpis") or []
        if kpis:
            story.append(
                _tiles(
                    [
                        (
                            k["label"],
                            _UNIT_FMT.get(k["unit"], num)(k.get("value")),
                            _TREND.get(k.get("trend"), "") + (f" ({signed(k['change_pct'])})" if k.get("change_pct") is not None else ""),
                            INK,
                        )
                        for k in kpis
                    ]
                )
            )
        if sec.get("text"):
            story += [Spacer(1, 1.5 * mm), Paragraph(_esc(sec["text"]), S["body"])]
        items = sec.get("items") or []
        if items:
            rows = [
                [it["date"], it["title"], ratio(it.get("volume_ratio")), signed(it.get("price_change_pct")), signed(it.get("spread_change_pct"))]
                for it in items
            ]
            story.append(_table(["Date", "Event", "Volume vs baseline", "Price change", "Spread change"], rows, [CONTENT_W * x for x in (0.12, 0.52, 0.14, 0.11, 0.11)], align_right_from=2))

    story += [Spacer(1, 2 * mm), *_demo_note(report.get("_data_status"))]
    return _build(story, title, report.get("generated_at"), report.get("disclaimer") or DISCLAIMER, one_page=True)
