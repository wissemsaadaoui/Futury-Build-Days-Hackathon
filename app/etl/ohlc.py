"""OHLC Xetra : XETRA_OHLC_YYYYMMDD.csv.gz (une ligne par instrument, devise et jour)."""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from app.etl._files import OHLC, daily_files

OHLC_COLS = [
    "date",
    "isin",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover_eur",
    "vwap",
    "close_mid",
    "open_auction_price",
    "mid_auction_price",
    "close_auction_price",
    "open_auction_ts",
    "mid_auction_ts",
    "close_auction_ts",
]

_TS = ["OPEN_AUCTION_PRICE_TS", "MID_AUCTION_PRICE_TS", "CLOSE_AUCTION_PRICE_TS"]
_USECOLS = [
    "FACT_DATE",
    "ISIN",
    "INSTRUMENT_NAME",
    "SEGMENT_NAME",
    "CURRENCY",
    "TRADED_VOLUME",
    "TRADED_VALUE",
    "OPEN_PRICE",
    "HIGH_PRICE",
    "LOW_PRICE",
    "CLOSE_PRICE",
    "OPEN_AUCTION_PRICE",
    "MID_AUCTION_PRICE",
    "CLOSE_AUCTION_PRICE",
    "VWAP",
    *_TS,
]


def _read(path) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=_USECOLS, dtype={"ISIN": str, **{c: str for c in _TS}})
    # Actions en EUR uniquement (les ETP et les lignes en devise étrangère sont exclus)
    return df[(df["SEGMENT_NAME"] == "EQUITIES") & (df["CURRENCY"] == "EUR")]


@lru_cache(maxsize=1)
def _raw() -> pd.DataFrame:
    files = daily_files(*OHLC)
    if not files:
        return pd.DataFrame(columns=_USECOLS)
    df = pd.concat((_read(f) for f in files), ignore_index=True)
    df["FACT_DATE"] = pd.to_datetime(df["FACT_DATE"]).dt.normalize()  # "2026-01-02 00:00:00"
    # Clé unique (date, isin) : en cas de doublon, garder la ligne au plus gros TRADED_VALUE
    df = df.sort_values("TRADED_VALUE", ascending=False).drop_duplicates(["FACT_DATE", "ISIN"])
    return df.sort_values(["ISIN", "FACT_DATE"]).reset_index(drop=True)


@lru_cache(maxsize=1)
def load_ohlc() -> pd.DataFrame:
    """date, isin, open, high, low, close, volume, turnover_eur
    + vwap, close_mid, {open,mid,close}_auction_price, {open,mid,close}_auction_ts (HH:MM:SS, heure de Francfort).

    open/high/low/close_mid = prix mid cotés ; close = prix de la closing auction (clôture officielle),
    sinon close_mid. volume en actions, turnover_eur en EUR. ADJUSTED_PRICE (obsolète) n'est pas utilisé.
    """
    raw = _raw()
    if raw.empty:
        return pd.DataFrame(columns=OHLC_COLS)
    df = pd.DataFrame(
        {
            "date": raw["FACT_DATE"],
            "isin": raw["ISIN"],
            "open": raw["OPEN_PRICE"],
            "high": raw["HIGH_PRICE"],
            "low": raw["LOW_PRICE"],
            "close": raw["CLOSE_AUCTION_PRICE"].fillna(raw["CLOSE_PRICE"]),
            "volume": raw["TRADED_VOLUME"].astype(float),
            "turnover_eur": raw["TRADED_VALUE"].astype(float),
            "vwap": raw["VWAP"],
            "close_mid": raw["CLOSE_PRICE"],
            "open_auction_price": raw["OPEN_AUCTION_PRICE"],
            "mid_auction_price": raw["MID_AUCTION_PRICE"],
            "close_auction_price": raw["CLOSE_AUCTION_PRICE"],
            "open_auction_ts": raw["OPEN_AUCTION_PRICE_TS"],
            "mid_auction_ts": raw["MID_AUCTION_PRICE_TS"],
            "close_auction_ts": raw["CLOSE_AUCTION_PRICE_TS"],
        }
    )
    return df[OHLC_COLS].reset_index(drop=True)


@lru_cache(maxsize=1)
def instrument_names() -> dict[str, str]:
    """ISIN -> INSTRUMENT_NAME (abrégé, majuscules) du dernier jour où l'action apparaît."""
    raw = _raw()
    if raw.empty:
        return {}
    last = raw.sort_values("FACT_DATE").drop_duplicates("ISIN", keep="last")
    return dict(zip(last["ISIN"], last["INSTRUMENT_NAME"].str.split().str.join(" ")))
