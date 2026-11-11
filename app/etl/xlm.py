"""Spreads XLM : dax_mdax_sdax_xlm.YYYYMMDD.csv (un fichier par jour, 174 actions)."""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from app.etl._files import SPREADS, daily_files

XLM_COLS = ["date", "isin", "mnemonic", "index", "notional", "impact_bps"]


@lru_cache(maxsize=1)
def load_xlm() -> pd.DataFrame:
    """date (datetime64), isin, mnemonic, index, notional (float), impact_bps (float, NaN possible)"""
    files = daily_files(*SPREADS)
    if not files:
        return pd.DataFrame(columns=XLM_COLS)
    df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    df = df.rename(
        columns={
            "Date": "date",
            "ISIN": "isin",
            "Mnemonic": "mnemonic",
            "Index": "index",
            "Notional_CCY": "notional",
            "Impact_bps": "impact_bps",
        }
    )
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d")
    df["notional"] = df["notional"].astype(float)
    # NaN = carnet pas assez profond pour ce notional : ne pas remplacer par 0
    df["impact_bps"] = pd.to_numeric(df["impact_bps"], errors="coerce")
    return df[XLM_COLS].sort_values(["isin", "date", "notional"]).reset_index(drop=True)
