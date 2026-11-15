"""Regenerate mocks/*.json from SYNTHETIC market data (no Deutsche Börse file is read).

The script builds a fake trading universe (random-walk prices, volumes, XLM spreads, flows and trades),
plugs it into app.etl, then runs the real analytics functions and writes their output to mocks/.
Every figure in the mocks is therefore synthetic but internally consistent
(ratio = value / 20-day baseline, z-scores, peers medians, auction shares...).

Only data/events.csv (public announcement dates and titles) and config.PEERS / config.NAMES are reused.

Run from the repo root:
    python -m scripts.make_synthetic_mocks
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date

import numpy as np
import pandas as pd

os.environ["LLM_PROVIDER"] = ""  # template summaries only, never an LLM call
os.environ["DECISIONS_DB"] = os.path.join(tempfile.mkdtemp(), "decisions.db")

from app import config, etl  # noqa: E402
from app.etl.flows import FLOWS_COLS  # noqa: E402
from app.etl.ohlc import OHLC_COLS  # noqa: E402
from app.etl.trades import TRADES_COLS  # noqa: E402
from app.etl.universe import UNIVERSE_COLS  # noqa: E402
from app.etl.xlm import XLM_COLS  # noqa: E402

SEED = 20261115
START, END = "2026-01-02", "2026-10-30"
NOTIONALS = [10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000, 2_500_000, 5_000_000]
HOLIDAYS = {"2026-04-03", "2026-04-06", "2026-05-01", "2026-12-24", "2026-12-25"}
DEMO = config.DEMO_ISINS[0]

# Synthetic universe: the demo issuer, its manual peers, and invented index members (fake ISINs, prefix ZZ).
PEER_INDEX = {"DE000FTG1111": "MDAX"}


def _universe() -> pd.DataFrame:
    rows = [(DEMO, config.NAMES[DEMO], "PBB", "SDAX")]
    mnemonics = {"DE000A161N30": "GLJ", "DE0005493365": "HYQ", "DE0006569908": "MLP",
                 "DE0006223407": "PCZ", "DE0008051004": "WUW", "DE000FTG1111": "FTK"}
    for p in config.PEERS[DEMO]:
        rows.append((p, config.NAMES.get(p, p), mnemonics.get(p, p[-4:]), PEER_INDEX.get(p, "SDAX")))
    for idx, n in (("SDAX", 14), ("MDAX", 10), ("DAX", 8)):
        for i in range(1, n + 1):
            isin = f"ZZ00SYN{idx[0]}{i:03d}0"
            rows.append((isin, f"Synthetic {idx} Company {i:02d} AG", f"S{idx[0]}{i:02d}", idx))
    u = pd.DataFrame(rows, columns=["isin", "name", "mnemonic", "index"])
    u["sector"] = u["isin"].map(config.SECTORS).fillna("")
    return u[UNIVERSE_COLS]


def _days() -> pd.DatetimeIndex:
    d = pd.bdate_range(START, END)
    return d[~d.strftime("%Y-%m-%d").isin(HOLIDAYS)]


def _shocks(days: pd.DatetimeIndex, rng: np.random.Generator) -> dict[tuple[str, pd.Timestamp], tuple[float, float, float]]:
    """(volume x, price jump, spread x) on each announcement day of data/events.csv (any issuer)."""
    from app.analytics import events as ev_mod

    out = {}
    ev = ev_mod.events_df()
    for isin, td in zip(ev["isin"], pd.to_datetime(ev["trading_day"])):
        if td in days:
            out[(isin, td)] = (rng.uniform(1.6, 3.4), rng.choice([-1, 1]) * rng.uniform(0.8, 4.5) / 100,
                               rng.uniform(1.05, 1.4))
    return out


def _simulate(u: pd.DataFrame, days: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    shocks = _shocks(days, rng)
    ohlc_rows, xlm_rows, flow_rows, trades = [], [], [], {}
    n = len(days)
    for r in u.itertuples():
        demo = r.isin == DEMO
        base_bps = {"DAX": 6.0, "MDAX": 18.0, "SDAX": 45.0}[r.index] * rng.uniform(0.6, 1.6)
        price = 8.0 if demo else float(np.exp(rng.uniform(np.log(6), np.log(180))))
        adv_eur = {"DAX": 8e7, "MDAX": 9e6, "SDAX": 1.5e6}[r.index] * rng.uniform(0.5, 1.8)
        sigma = rng.uniform(0.012, 0.028)
        auction_base = rng.uniform(0.18, 0.34)
        rets = rng.normal(0.0002, sigma, n)
        spread_mult = np.exp(rng.normal(0, 0.12, n))
        vol_mult = np.exp(rng.normal(0, 0.35, n))
        spikes = rng.random(n) < 0.02
        vol_mult[spikes] *= rng.uniform(2.5, 4.5, spikes.sum())
        wide = rng.random(n) < 0.012
        spread_mult[wide] *= rng.uniform(1.5, 2.0, wide.sum())
        if demo:  # a gradual synthetic widening over the summer, for the dashboard key finding
            spread_mult *= np.interp(np.arange(n), [0, 110, 150, n - 1], [0.9, 0.95, 1.3, 1.35])
        buy_bias = np.clip(rng.normal(0.5, 0.05, n), 0.3, 0.7)
        for i, d in enumerate(days):
            vm, jump, sm = shocks.get((r.isin, d), (1.0, 0.0, 1.0))
            open_ = price * (1 + rng.normal(0, sigma / 3))
            close = max(0.5, price * (1 + rets[i] + jump))
            volume_eur = adv_eur * vol_mult[i] * vm
            shares = max(200, int(volume_eur / ((open_ + close) / 2)))
            a_share = float(np.clip(auction_base + rng.normal(0, 0.06), 0.05, 0.9))
            auction_qty = int(shares * a_share)
            cont_qty = shares - auction_qty
            # continuous trades: Brownian bridge open -> close
            k = int(np.clip(rng.poisson(320 if demo else 120), 20, 600))
            t = np.sort(rng.uniform(9 * 3600 + 30, 17.5 * 3600 - 5, k))
            w = np.cumsum(rng.normal(0, sigma / np.sqrt(k), k))
            w -= np.linspace(0, 1, k) * w[-1]
            px = np.round(open_ + (close - open_) * (t - t[0]) / max(t[-1] - t[0], 1) + open_ * w, 3)
            qty = rng.lognormal(0, 1, k)
            qty = np.maximum(1, np.floor(qty / qty.sum() * cont_qty)).astype(int)
            qty[-1] += max(0, cont_qty - qty.sum())
            side = np.where(rng.random(k) < buy_bias[i], "BUY", "SELL")
            a_open, a_mid = int(auction_qty * 0.25), int(auction_qty * 0.08)
            a_close = auction_qty - a_open - a_mid
            p_open, p_mid, p_close = round(open_, 3), round(float(np.median(px)), 3), round(close, 3)
            auc = [(9 * 3600 + rng.integers(1, 120), p_open, a_open, "opening"),
                   (13 * 3600 + rng.integers(60, 240), p_mid, a_mid, "midday"),
                   (17 * 3600 + 35 * 60 + rng.integers(0, 90), p_close, a_close, "closing")]
            secs = np.concatenate([t, [a[0] for a in auc]])
            prices = np.concatenate([px, [a[1] for a in auc]])
            qtys = np.concatenate([qty, [a[2] for a in auc]]).astype(int)
            sides = np.concatenate([side, ["", "", ""]])
            atype = np.array([""] * k + [a[3] for a in auc])
            local = (pd.Timestamp(d).tz_localize(config.TZ) + pd.to_timedelta(secs, unit="s"))
            tdf = pd.DataFrame({"ts_local": local, "price": prices, "qty": qtys, "side": sides, "auction_type": atype})
            tdf = tdf[tdf["qty"] > 0]
            tdf["ts_utc"] = tdf["ts_local"].dt.tz_convert("UTC")
            tdf["date"] = pd.Timestamp(d)
            tdf["notional_eur"] = (tdf["price"] * tdf["qty"]).round(2)
            tdf["is_auction"] = tdf["side"] == ""
            trades.setdefault(r.isin, []).append(tdf)
            vol = float(tdf["qty"].sum())
            turnover = float(tdf["notional_eur"].sum())
            hi, lo = float(tdf["price"].max()), float(tdf["price"].min())
            ts = lambda s: f"{int(s) // 3600:02d}:{int(s) % 3600 // 60:02d}:{int(s) % 60:02d}"  # noqa: E731
            ohlc_rows.append((d, r.isin, round(open_, 3), hi, lo, p_close, vol, round(turnover, 1),
                              round(turnover / vol, 3), round(float(px[-1]), 3), p_open, p_mid if a_mid else np.nan,
                              p_close, ts(auc[0][0]), ts(auc[1][0]) if a_mid else np.nan, ts(auc[2][0])))
            # XLM: cost of a round trip grows with the notional; NaN when the book is too thin
            bps25 = base_bps * spread_mult[i] * sm
            depth = adv_eur * rng.uniform(0.02, 0.08)
            for notional in NOTIONALS:
                bps = round(bps25 * (notional / 25_000) ** 0.4, 2) if notional <= depth else np.nan
                xlm_rows.append((d, r.isin, r.mnemonic, r.index, float(notional), bps))
            # Flows: aggressive side of each continuous trade, passive = the other side, auctions on both sides
            cont = tdf[~tdf["is_auction"]]
            vwap = turnover / vol
            agg = {s: float(cont.loc[cont["side"] == s, "qty"].sum()) for s in ("BUY", "SELL")}
            mode_side = {("AGGRESSIVE", "BUY"): agg["BUY"], ("AGGRESSIVE", "SELL"): agg["SELL"],
                         ("PASSIVE", "BUY"): agg["SELL"], ("PASSIVE", "SELL"): agg["BUY"],
                         ("AUCTION", "BUY"): float(auction_qty), ("AUCTION", "SELL"): float(auction_qty)}
            for (mode, s), v in mode_side.items():
                split = rng.dirichlet([3, 2, 4])
                for part, f in zip(("AGENT", "PROP", "MARKET_MAKER"), split):
                    qv = float(np.floor(v * f))
                    flow_rows.append((d, r.isin, part, mode, s, qv, round(qv * vwap, 1), 1))
            price = close
    tr = {}
    for isin, parts in trades.items():
        df = pd.concat(parts, ignore_index=True).sort_values("ts_utc", kind="stable").reset_index(drop=True)
        tr[isin] = df[TRADES_COLS]
    return {
        "ohlc": pd.DataFrame(ohlc_rows, columns=OHLC_COLS),
        "xlm": pd.DataFrame(xlm_rows, columns=XLM_COLS).sort_values(["isin", "date", "notional"]).reset_index(drop=True),
        "flows": pd.DataFrame(flow_rows, columns=FLOWS_COLS).sort_values(["isin", "date"], kind="stable").reset_index(drop=True),
        "trades": tr,
    }


def install() -> None:
    """Replace the ETL loaders by the synthetic data (in this process only)."""
    u = _universe()
    days = _days()
    etl.get_universe = lambda: u  # events_df needs the trading calendar first: provisional XLM
    etl.load_xlm = lambda: pd.DataFrame({"date": days, "isin": DEMO, "mnemonic": "PBB", "index": "SDAX",
                                         "notional": 25_000.0, "impact_bps": 1.0})
    from app.analytics import data

    data.clear_caches()
    sim = _simulate(u, days)
    empty_trades = pd.DataFrame(columns=TRADES_COLS)
    etl.load_xlm = lambda: sim["xlm"]
    etl.load_ohlc = lambda: sim["ohlc"]
    etl.load_flows = lambda: sim["flows"]
    etl.load_trades = lambda isin: sim["trades"].get(isin, empty_trades)
    etl.index_on_date = lambda isin, day: u.set_index("isin")["index"].get(isin)
    data.clear_caches()


NOTE = "Synthetic data: every figure is generated by scripts/make_synthetic_mocks.py (no real market data)."
FIXED_TS = "2026-11-15T10:00:00+01:00"


def _write(name: str, endpoint: str, payload: dict) -> None:
    payload = json.loads(json.dumps(payload))
    for key in ("generated_at",):
        if key in payload:
            payload[key] = FIXED_TS
    out = {"_endpoint": endpoint, **payload, "_note": NOTE}
    path = config.MOCKS_DIR / f"{name}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(config.ROOT)}")


def main() -> None:
    install()
    from app import analytics as A

    ev = A.list_events(DEMO)
    stocks = A.list_stocks()
    stocks["stocks"] = [s for s in stocks["stocks"] if s["isin"] == DEMO]
    _write("stocks", "GET /stocks", stocks)
    _write("dashboard", "GET /stocks/{isin}/dashboard?from=2026-08-17&to=2026-10-09",
           A.build_dashboard(DEMO, date(2026, 8, 17), date(2026, 10, 9)))
    _write("events", "GET /stocks/{isin}/events", ev)
    _write("impact-card", "GET /events/{event_id}/impact-card   (also GET /days/{isin}/{date}/impact-card, with \"event\": null)",
           A.build_impact_card("evt_002"))
    _write("impact-card-voting-rights", "GET /events/{event_id}/impact-card   (voting_rights event: pre_disclosure_activity block)",
           A.build_impact_card("evt_019"))
    _write("compare", "GET /compare?type=quarterly_results&index=SDAX&from=2025-11-01&to=2026-10-31",
           A.compare_events("quarterly_results", "SDAX", date(2025, 11, 1), date(2026, 10, 31)))
    _write("report", "GET /stocks/{isin}/report?from=2026-01-02&to=2026-10-30   (IR snapshot)",
           A.build_report(DEMO, date(2026, 1, 2), date(2026, 10, 30)))
    _write("event-preview", "GET /stocks/{isin}/event-preview?type=quarterly_results   (date= optional)",
           A.build_event_preview(DEMO, "quarterly_results"))


if __name__ == "__main__":
    main()
