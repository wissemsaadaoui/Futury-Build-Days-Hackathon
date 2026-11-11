"""Flows Xetra : XETRA_FLOW_DYNAMICS_EQUITY_YYYYMMDD.csv.gz (format large, 73 colonnes) -> format long."""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from app.etl._files import FLOWS, daily_files

FLOWS_COLS = ["date", "isin", "participant", "mode", "side", "volume", "notional_eur", "n_days"]

PARTICIPANTS = {"MM": "MARKET_MAKER", "AGENT": "AGENT", "PROP": "PROP"}
MODES = ["AGGRESSIVE", "PASSIVE", "AUCTION"]
SIDES = ["BUY", "SELL"]

_FLOW_COLS = [f"{p}_{m}_{s}_EXECUTION_{k}" for p in PARTICIPANTS for m in MODES for s in SIDES for k in ("QTY", "VOLUME")]
_USECOLS = ["ISIN", "SECURITY_TYPE", "REPORTED_FLOW_DATES", *_FLOW_COLS]


def _read(path) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=_USECOLS, dtype={"ISIN": str, "REPORTED_FLOW_DATES": str})
    # Actions (CS) uniquement ; REPORTED_FLOW_DATES vide = flux censuré (< 7 exécutions), publié plus tard
    return df[(df["SECURITY_TYPE"] == "CS") & df["REPORTED_FLOW_DATES"].notna()]


@lru_cache(maxsize=1)
def load_flows() -> pd.DataFrame:
    """date, isin, participant (AGENT|PROP|MARKET_MAKER), mode (AGGRESSIVE|PASSIVE|AUCTION), side (BUY|SELL),
    volume (actions), notional_eur, n_days.

    La date vient de REPORTED_FLOW_DATES (pas de la colonne DATE). Une ligne couvrant plusieurs jours
    ("2026-05-29, 2026-06-01") est attribuée au dernier jour, avec n_days = nombre de jours agrégés.
    Les lignes DELAYED_RELEASE = 1 sont traitées de la même façon (elles portent des dates antérieures).
    La colonne VOLUME du fichier (achat + vente, comptée deux fois) n'est pas utilisée.
    """
    files = daily_files(*FLOWS)
    if not files:
        return pd.DataFrame(columns=FLOWS_COLS)
    wide = pd.concat((_read(f) for f in files), ignore_index=True)
    dates = wide["REPORTED_FLOW_DATES"].str.split(", ")
    wide["date"] = pd.to_datetime(dates.str[-1])
    wide["n_days"] = dates.str.len().astype("int8")

    parts = []
    for p, participant in PARTICIPANTS.items():
        for m in MODES:
            for s in SIDES:
                parts.append(
                    pd.DataFrame(
                        {
                            "date": wide["date"],
                            "isin": wide["ISIN"],
                            "participant": participant,
                            "mode": m,
                            "side": s,
                            "volume": wide[f"{p}_{m}_{s}_EXECUTION_QTY"],
                            "notional_eur": wide[f"{p}_{m}_{s}_EXECUTION_VOLUME"],
                            "n_days": wide["n_days"],
                        }
                    )
                )
    df = pd.concat(parts, ignore_index=True)
    df["isin"] = df["isin"].astype("category")  # ~2,6 M lignes : divise la mémoire par ~3
    for col, values in (("participant", list(PARTICIPANTS.values())), ("mode", MODES), ("side", SIDES)):
        df[col] = pd.Categorical(df[col], categories=values)
    df["volume"] = df["volume"].fillna(0.0).astype(float)
    df["notional_eur"] = df["notional_eur"].fillna(0.0).astype(float)
    return df.sort_values(["isin", "date"], kind="stable").reset_index(drop=True)[FLOWS_COLS]
