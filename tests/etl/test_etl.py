from __future__ import annotations

import pandas as pd
import pytest

from app import config, etl
from app.etl.trades import trades_path

PBB = "DE0008019001"

needs_raw = pytest.mark.skipif(etl.load_ohlc().empty, reason="data/raw/XETRA absent")
needs_trades = pytest.mark.skipif(not trades_path(PBB).exists(), reason="lancer : python -m scripts.extract_trades")


# ---------- colonnes exactes (contrat CLAUDE.md) ----------
@pytest.mark.parametrize(
    "loader, cols",
    [
        (etl.load_xlm, etl.XLM_COLS),
        (etl.load_ohlc, etl.OHLC_COLS),
        (etl.load_flows, etl.FLOWS_COLS),
        (etl.load_events, etl.EVENTS_COLS),
        (etl.get_universe, ["isin", "name", "mnemonic", "index", "sector"]),
        (lambda: etl.load_trades(PBB), etl.TRADES_COLS),
    ],
)
def test_exact_columns(loader, cols) -> None:
    assert list(loader().columns) == cols


def test_missing_trades_file_gives_empty_frame() -> None:
    df = etl.load_trades("XX0000000000")
    assert df.empty and list(df.columns) == etl.TRADES_COLS


# ---------- OHLC ----------
@needs_raw
def test_ohlc_unique_date_isin() -> None:
    o = etl.load_ohlc()
    assert not o.duplicated(["date", "isin"]).any()
    assert pd.api.types.is_datetime64_any_dtype(o["date"])
    assert o["date"].nunique() == 213


@needs_raw
def test_ohlc_close_is_closing_auction() -> None:
    o = etl.load_ohlc()
    p = o[(o["isin"] == PBB) & o["close_auction_price"].notna()]
    assert not p.empty
    assert (p["close"] == p["close_auction_price"]).all()


# ---------- Flows ----------
@needs_raw
def test_flows_normalized_values() -> None:
    f = etl.load_flows()
    assert set(f["participant"].unique()) == {"AGENT", "PROP", "MARKET_MAKER"}
    assert set(f["mode"].unique()) == {"AGGRESSIVE", "PASSIVE", "AUCTION"}
    assert set(f["side"].unique()) == {"BUY", "SELL"}
    assert not f.duplicated(["date", "isin", "participant", "mode", "side"]).any()
    assert (f["n_days"] >= 1).all()


@needs_raw
def test_flows_pbb_buy_equals_sell_on_single_day_rows() -> None:
    f = etl.load_flows()
    p = f[(f["isin"] == PBB) & (f["n_days"] == 1)]
    by_side = p.groupby(["date", "side"], observed=True)["volume"].sum().unstack()
    assert len(by_side) > 200
    assert (by_side["BUY"] - by_side["SELL"]).abs().max() < 1e-6


@needs_raw
def test_flows_volume_matches_ohlc_volume() -> None:
    """volume des Flows = actions comptées une fois : achats totaux = volume OHLC du jour."""
    f, o = etl.load_flows(), etl.load_ohlc()
    day = pd.Timestamp("2026-09-29")
    buy = f[(f["isin"] == PBB) & (f["date"] == day) & (f["side"] == "BUY")]["volume"].sum()
    assert buy == o[(o["isin"] == PBB) & (o["date"] == day)]["volume"].iloc[0]


# ---------- Univers / indices ----------
@needs_raw
def test_universe_and_index_on_date() -> None:
    u = etl.get_universe().set_index("isin")
    assert len(u) == 174
    assert u.loc[PBB, "name"] == config.NAMES[PBB]
    assert (u.loc[PBB, "mnemonic"], u.loc[PBB, "index"]) == ("PBB", "SDAX")
    assert etl.index_on_date(PBB, "2026-06-06") == "SDAX"  # samedi -> jour de trading précédent
    assert etl.index_on_date("DE0006223407", "2026-10-13") is None  # ProCredit : SDAX dès le 14.10
    assert etl.index_on_date("DE0006223407", "2026-10-14") == "SDAX"


# ---------- Trades ----------
@needs_trades
def test_trades_sorted_and_consistent() -> None:
    t = etl.load_trades(PBB)
    assert t["ts_utc"].is_monotonic_increasing
    assert set(t["side"].unique()) <= {"BUY", "SELL", ""}
    assert (t["is_auction"] == (t["side"] == "")).all()
    assert set(t["auction_type"].unique()) <= {"opening", "midday", "closing", ""}
    assert not t.loc[~t["is_auction"], "auction_type"].astype(bool).any()
    assert str(t["ts_local"].dt.tz) == config.TZ


@needs_trades
def test_auction_trades_match_ohlc_auction_prices() -> None:
    t = etl.load_trades(PBB)
    o = etl.load_ohlc()
    o = o[o["isin"] == PBB].set_index("date")
    closing = t[t["auction_type"] == "closing"].groupby("date")["price"].first()
    assert len(closing) > 200
    assert (closing == o["close_auction_price"].reindex(closing.index)).all()
