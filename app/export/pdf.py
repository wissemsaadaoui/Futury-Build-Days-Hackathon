"""Mise en page PDF (reportlab) des sorties de app.analytics : aucun calcul, uniquement de la présentation."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
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
def _window_chart(window: list[dict]) -> Drawing:
    """Volume relatif (× baseline) sur la fenêtre −5…+5, jour de l'événement en couleur."""
    w, h = CONTENT_W, 38 * mm
    d = Drawing(w, h)
    values = [p.get("volume_ratio") or 0 for p in window]
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 9 * mm, 7 * mm, w - 12 * mm, h - 13 * mm
    chart.data = [values]
    chart.categoryAxis.categoryNames = [f"{p['offset']:+d}" if p["offset"] else "0" for p in window]
    chart.categoryAxis.labels.fontSize = 6.5
    chart.categoryAxis.strokeColor = RULE
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontSize = 6.5
    chart.valueAxis.strokeColor = RULE
    chart.valueAxis.gridStrokeColor = RULE
    chart.valueAxis.visibleGrid = True
    chart.bars[0].fillColor = colors.HexColor("#9fb3c8")
    chart.bars[0].strokeColor = None
    for i, p in enumerate(window):
        if p["offset"] == 0:
            chart.bars[(0, i)].fillColor = ACCENT
    d.add(chart)
    d.add(String(9 * mm, h - 4 * mm, "Volume vs 20-day baseline (×), trading days −5 to +5", fontSize=7, fillColor=MUTED))
    return d


def impact_card_pdf(card: dict) -> bytes:
    stock, ev, m = card["stock"], card.get("event"), card["metrics"]
    if ev:
        title = f"{stock['name']} – {ev['title']}"
        when = (ev.get("published_at") or ev["trading_day"])[:16].replace("T", " ")
        sub = f"{_stock_line(stock)}<br/>{_esc(ev['type'].replace('_', ' '))} · published {_esc(when)} · measured on trading day {_esc(ev['trading_day'])}"
        if ev.get("source_url"):
            sub += f' · <link href="{_esc(ev["source_url"])}" color="#0b5cad">source</link>'
    else:
        day = next((p["date"] for p in card.get("window", []) if p["offset"] == 0), "")
        title = f"{stock['name']} – notable trading day {day}"
        sub = f"{_stock_line(stock)}<br/>No announcement linked to this day"
    b = card["baseline"]
    sub += f"<br/>Baseline: {_esc(b['method'])} ({_esc(b['from'])} to {_esc(b['to'])})"

    vol, price, spread, auc = m["volume"], m["price"], m["spread_bps"], m["auction_share"]
    story: list[Flowable] = _header(title, sub)
    story += [
        Spacer(1, 3 * mm),
        _tiles(
            [
                ("Volume vs baseline", ratio(vol.get("ratio")), f"z-score {num(vol.get('z_score'), 1)}", INK),
                ("Price change", signed(price.get("change_pct")), f"close {num(price.get('close'), 2)} EUR", _color(price.get("change_pct"))),
                ("Spread (25k EUR)", num(spread.get("event"), 1, " bps"), f"{signed(spread.get('change_pct'))} vs {num(spread.get('baseline'), 1)} bps", INK),
                ("Auction share", share(auc.get("event")), f"normal {share(auc.get('baseline'))}", INK),
            ]
        ),
        Paragraph("Summary", S["h2"]),
        Paragraph(_esc(card.get("ai_summary") or "–"), S["body"]),
        Paragraph("Key metrics", S["h2"]),
    ]
    oa, ca, to = m["opening_auction"], m["closing_auction"], m["turnover_eur"]
    status = card.get("_data_status") or {}
    auction_tag = "" if status.get("opening_closing_auction", "real") == "real" else " (demo data)"
    metrics_rows = [
        ["Volume (shares)", num(vol.get("event")), num(vol.get("baseline")), ratio(vol.get("ratio"))],
        ["Turnover (EUR)", num(to.get("event")), num(to.get("baseline")), ratio(to.get("ratio"))],
        ["Spread, 25k EUR (bps)", num(spread.get("event"), 1), num(spread.get("baseline"), 1), signed(spread.get("change_pct"))],
        ["Auction share", share(auc.get("event")), share(auc.get("baseline")), signed(None if auc.get("change_pts") is None else auc["change_pts"] * 100, 1, " pts")],
        [f"Opening auction (shares){auction_tag}", num(oa.get("volume")), num(oa.get("baseline")), ratio(oa.get("ratio"))],
        [f"Closing auction (shares){auction_tag}", num(ca.get("volume")), num(ca.get("baseline")), ratio(ca.get("ratio"))],
    ]
    price_rows = [
        ["Previous close", num(price.get("prev_close"), 2)],
        ["Open", num(price.get("open"), 2)],
        ["Close", num(price.get("close"), 2)],
        ["Change", signed(price.get("change_pct"))],
        ["Intraday range", num(price.get("intraday_range_pct"), 1, "%")],
    ]
    left_w = CONTENT_W * 0.64
    gap = CONTENT_W * 0.04
    right_w = CONTENT_W - left_w - gap
    side = Table(
        [[
            _table(["Metric", "Event day", "Baseline", "Change"], metrics_rows, [left_w * 0.4, left_w * 0.22, left_w * 0.22, left_w * 0.16]),
            "",
            _table(["Price (EUR)", ""], price_rows, [right_w * 0.6, right_w * 0.4]),
        ]],
        colWidths=[left_w, gap, right_w],
    )
    side.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(side)

    flows = card["flows"]
    fl_rows = [[p["type"].replace("_", " ").title(), num(p.get("buy")), num(p.get("sell")), signed(p.get("net"), 0, "")] for p in flows["by_participant"]]
    mode_rows = [[x["mode"].title(), share(x.get("share"))] for x in flows["by_mode"]]
    side2 = Table(
        [[
            _table(["Participant", "Bought", "Sold", "Net"], fl_rows, [left_w * 0.34, left_w * 0.22, left_w * 0.22, left_w * 0.22]),
            "",
            _table(["Market mode", "Share"], mode_rows, [right_w * 0.6, right_w * 0.4]),
        ]],
        colWidths=[left_w, gap, right_w],
    )
    side2.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [Paragraph("Order flow by participant (shares)", S["h2"]), side2]

    if card.get("window"):
        story += [Paragraph("Around the event", S["h2"]), _window_chart(card["window"])]
        w_rows = [
            [f"{p['offset']:+d}" if p["offset"] else "0", p["date"], num(p.get("close"), 2), ratio(p.get("volume_ratio")), num(p.get("spread_bps"), 1)]
            for p in card["window"]
        ]
        story.append(_table(["Day", "Date", "Close (EUR)", "Volume vs baseline", "Spread (bps)"], w_rows, [CONTENT_W * x for x in (0.1, 0.25, 0.2, 0.25, 0.2)]))

    vp, tc = card["vs_peers"], card["technical_context"]
    lvl = tc.get("broke_level")
    context = [
        ["Peer median volume vs baseline", ratio(vp.get("peer_avg_volume_ratio"))],
        ["Peer median price change", signed(vp.get("peer_avg_price_change_pct"))],
        ["Excess return vs peers", signed(vp.get("excess_return_pct"), 1, " pts")],
        ["Trend before (EMA 50)", tc["trend_before"].replace("_", " ")],
        ["MACD before / after", f"{tc['macd_before']} / {tc['macd_after']}"],
        ["Price level crossed", f"{lvl['type']} at {num(lvl['price'], 2)} EUR" if lvl else "none"],
    ]
    story += [Paragraph("Peers and technical context (descriptive only)", S["h2"]), _table(["", ""], context, [CONTENT_W * 0.5, CONTENT_W * 0.5])]
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
