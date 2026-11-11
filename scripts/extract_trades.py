"""Extrait les trades on-book Xetra des actions de démo et de leurs peers.

Lit les 213 fichiers XETRA_ONBOOK_TRADES_YYYYMMDD.csv.gz (~400 000 trades/jour, tous instruments) jour par jour,
garde les ISIN de config.DEMO_ISINS + config.PEERS et écrit data/processed/trades_<ISIN>.csv.gz
(colonnes : app.etl.trades.TRADES_COLS), lu ensuite par app.etl.load_trades(isin).

Lancer depuis la racine du repo :
    python -m scripts.extract_trades                 # démo + peers
    python -m scripts.extract_trades DE0008019001    # ISIN choisis
"""
from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from app import config, etl
from app.etl._files import TRADES, daily_files
from app.etl.trades import TRADES_COLS, trades_path

AUCTIONS = {"opening": "open_auction_ts", "midday": "mid_auction_ts", "closing": "close_auction_ts"}
AUCTION_TOLERANCE_S = 2


def _read_day(args: tuple[Path, frozenset[str]]) -> pd.DataFrame:
    path, isins = args
    df = pd.read_csv(
        path,
        usecols=["FACT_TIMESTAMP", "ISIN", "QUANTITY", "PRICE", "SIDE", "CURRENCY"],
        dtype={"ISIN": str, "SIDE": "Int8", "CURRENCY": str},
    )
    return df[df["ISIN"].isin(isins) & (df["CURRENCY"] == "EUR")]


def _auction_type(trades: pd.DataFrame, ohlc: pd.DataFrame) -> pd.Series:
    """opening | midday | closing si le trade sans agresseur tombe à ±2 s d'une enchère de l'OHLC du jour, sinon ""."""
    out = pd.Series("", index=trades.index, dtype=object)
    secs = trades["ts_local"].dt.hour * 3600 + trades["ts_local"].dt.minute * 60 + trades["ts_local"].dt.second
    key = pd.MultiIndex.from_arrays([trades["date"], trades["isin"]])
    o = ohlc.set_index(["date", "isin"])
    for name, col in AUCTIONS.items():
        ts = o[col].reindex(key)
        auction_secs = pd.to_timedelta(ts.to_numpy(), errors="coerce").total_seconds()
        hit = trades["is_auction"].to_numpy() & (np.abs(secs.to_numpy() - auction_secs) <= AUCTION_TOLERANCE_S)
        out[hit & (out == "").to_numpy()] = name
    return out


def extract(isins: list[str], workers: int) -> dict[str, int]:
    files = daily_files(*TRADES)
    if not files:
        raise SystemExit(f"Aucun fichier trades dans {config.DATA_DIR / TRADES[0]}")
    wanted = frozenset(isins)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        raw = pd.concat(pool.map(_read_day, [(f, wanted) for f in files], chunksize=4), ignore_index=True)

    ts_utc = pd.to_datetime(raw["FACT_TIMESTAMP"], utc=True, format="ISO8601")
    trades = pd.DataFrame(
        {
            "isin": raw["ISIN"],
            "ts_utc": ts_utc,
            "ts_local": ts_utc.dt.tz_convert(config.TZ),
            "price": raw["PRICE"].astype(float),
            "qty": raw["QUANTITY"].astype(int),
            "side": raw["SIDE"].map({1: "BUY", 2: "SELL"}).fillna(""),
        }
    )
    trades["date"] = trades["ts_local"].dt.tz_localize(None).dt.normalize()
    trades["notional_eur"] = trades["price"] * trades["qty"]
    trades["is_auction"] = trades["side"] == ""
    trades["auction_type"] = _auction_type(trades, etl.load_ohlc())

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    counts = {}
    for isin in isins:
        t = trades[trades["isin"] == isin].sort_values("ts_utc", kind="stable")
        out = t[TRADES_COLS].copy()
        out["date"] = out["date"].dt.strftime("%Y-%m-%d")
        out.to_csv(trades_path(isin), index=False, compression="gzip")
        counts[isin] = len(t)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("isins", nargs="*", help="ISIN à extraire (défaut : DEMO_ISINS + leurs PEERS)")
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    args = parser.parse_args()
    isins = args.isins or list(dict.fromkeys(i for d in config.DEMO_ISINS for i in (d, *config.PEERS.get(d, []))))

    start = time.perf_counter()
    counts = extract(isins, args.workers)
    names = etl.get_universe().set_index("isin")["name"].to_dict()
    for isin, n in counts.items():
        print(f"{isin}  {names.get(isin, ''):35s} {n:>9,} trades -> {trades_path(isin).relative_to(config.ROOT)}")
    print(f"Durée : {time.perf_counter() - start:.1f} s")


if __name__ == "__main__":
    main()
