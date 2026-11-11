"""Univers DAX/MDAX/SDAX : index_constituents/[INDEX]_CONSTITUENTS_YYYYMMDD.csv.gz."""
from __future__ import annotations

from datetime import date
from functools import lru_cache

import pandas as pd

from app import config
from app.etl._files import CONSTITUENTS, daily_files
from app.etl.ohlc import instrument_names

CONSTITUENTS_COLS = ["date", "isin", "mnemonic", "index"]
UNIVERSE_COLS = ["isin", "name", "mnemonic", "index", "sector"]


@lru_cache(maxsize=1)
def load_constituents() -> pd.DataFrame:
    """date, isin, mnemonic, index – une ligne par constituant et par jour de trading."""
    files = daily_files(*CONSTITUENTS)
    if not files:
        return pd.DataFrame(columns=CONSTITUENTS_COLS)
    df = pd.concat((pd.read_csv(f, dtype=str, usecols=["Index", "Date", "Mnemonic", "Isin"]) for f in files), ignore_index=True)
    df = df.rename(columns={"Index": "index", "Date": "date", "Mnemonic": "mnemonic", "Isin": "isin"})
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    return df[CONSTITUENTS_COLS].sort_values(["isin", "date"]).reset_index(drop=True)


def index_on_date(isin: str, day: date | str | pd.Timestamp) -> str | None:
    """Indice de l'action à cette date (DAX | MDAX | SDAX), None si hors des trois indices.

    Sans fichier pour ce jour : liste du jour de trading précédent (NOTES.md). Si l'action figure dans deux
    indices le même jour (spin-off ajouté pour un jour), l'indice le plus grand est renvoyé.
    """
    c = load_constituents()
    if c.empty:
        return None
    known = c["date"].unique()
    day = pd.Timestamp(day)
    prior = known[known <= day]
    if len(prior) == 0:
        return None
    rows = c[(c["date"] == prior.max()) & (c["isin"] == isin)]
    for idx in ("DAX", "MDAX", "SDAX"):
        if idx in set(rows["index"]):
            return idx
    return None


@lru_cache(maxsize=1)
def get_universe() -> pd.DataFrame:
    """isin, name, mnemonic, index (actuel), sector (peut être vide)

    Une ligne par ISIN ayant été dans le DAX, MDAX ou SDAX sur la période ; index = dernier indice connu.
    name : config.NAMES, sinon INSTRUMENT_NAME de l'OHLC, sinon le mnemonic.
    """
    c = load_constituents()
    if c.empty:
        return pd.DataFrame(columns=UNIVERSE_COLS)
    rank = c["index"].map({"DAX": 0, "MDAX": 1, "SDAX": 2})
    last = c.assign(rank=rank).sort_values(["date", "rank"], ascending=[True, False]).drop_duplicates("isin", keep="last")
    names = instrument_names()
    last["name"] = [config.NAMES.get(i) or names.get(i) or m for i, m in zip(last["isin"], last["mnemonic"])]
    last["sector"] = last["isin"].map(config.SECTORS).fillna("")
    return last[UNIVERSE_COLS].sort_values("isin").reset_index(drop=True)
