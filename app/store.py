"""Stockage local SQLite : data/decisions.db (créé automatiquement, gitignoré).

Tables :
- thresholds(isin, key, value, updated_at, updated_by) : seuils d'alerte personnalisés (absents = défauts du code)
- decisions(id, item_type, item_id, isin, decision, note, old_value, new_value, decided_at, decided_by) :
  journal human-in-the-loop (approved / dismissed sur alertes, anomalies, résumés IA ; threshold_changed).

Chemin : variable d'environnement DECISIONS_DB (tests : base temporaire), sinon data/decisions.db.
Une connexion par appel : simple et sûr avec les threads de FastAPI.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from app import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS thresholds (
    isin TEXT NOT NULL,
    key TEXT NOT NULL,
    value REAL NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    PRIMARY KEY (isin, key)
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL,
    item_id TEXT NOT NULL,
    isin TEXT NOT NULL,
    decision TEXT NOT NULL,
    note TEXT,
    old_value TEXT,
    new_value TEXT,
    decided_at TEXT NOT NULL,
    decided_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS decisions_item ON decisions (isin, item_type, item_id);
"""


def db_path() -> Path:
    p = Path(os.getenv("DECISIONS_DB") or config.ROOT / "data" / "decisions.db")
    return p if p.is_absolute() else config.ROOT / p


def now_berlin() -> str:
    return datetime.now(ZoneInfo(config.TZ)).isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(_SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


# ---------------------------------------------------------------- seuils
def get_thresholds(isin: str) -> dict[str, float]:
    with connect() as con:
        return {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM thresholds WHERE isin = ?", (isin,))}


def set_thresholds(isin: str, values: dict[str, float], by: str) -> None:
    at = now_berlin()
    with connect() as con:
        con.executemany(
            "INSERT INTO thresholds (isin, key, value, updated_at, updated_by) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (isin, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at, "
            "updated_by = excluded.updated_by",
            [(isin, k, float(v), at, by) for k, v in values.items()],
        )


def delete_thresholds(isin: str, keys: list[str] | None = None) -> None:
    with connect() as con:
        if keys is None:
            con.execute("DELETE FROM thresholds WHERE isin = ?", (isin,))
        else:
            con.executemany("DELETE FROM thresholds WHERE isin = ? AND key = ?", [(isin, k) for k in keys])


# ---------------------------------------------------------------- journal des décisions
def add_decision(item_type: str, item_id: str, isin: str, decision: str, by: str, note: str | None = None,
                 old_value: Any = None, new_value: Any = None) -> dict:
    row = {
        "item_type": item_type, "item_id": item_id, "isin": isin, "decision": decision,
        "note": note or None,
        "old_value": None if old_value is None else str(old_value),
        "new_value": None if new_value is None else str(new_value),
        "decided_at": now_berlin(), "decided_by": by,
    }
    with connect() as con:
        cur = con.execute(
            "INSERT INTO decisions (item_type, item_id, isin, decision, note, old_value, new_value, decided_at, decided_by) "
            "VALUES (:item_type, :item_id, :isin, :decision, :note, :old_value, :new_value, :decided_at, :decided_by)",
            row,
        )
        row["id"] = cur.lastrowid
    return row


def list_decisions(isin: str | None = None, limit: int = 500) -> list[dict]:
    sql = "SELECT * FROM decisions" + (" WHERE isin = ?" if isin else "") + " ORDER BY id DESC LIMIT ?"
    args: tuple = (isin, limit) if isin else (limit,)
    with connect() as con:
        return [dict(r) for r in con.execute(sql, args)]


def latest_decisions(isin: str, item_types: tuple[str, ...] = ("alert", "anomaly", "ai_summary")) -> dict[tuple[str, str], dict]:
    """Dernière décision approved/dismissed par (item_type, item_id) : c'est elle qui fait foi."""
    marks = ",".join("?" * len(item_types))
    sql = (f"SELECT * FROM decisions WHERE isin = ? AND item_type IN ({marks}) "
           "AND decision IN ('approved', 'dismissed') ORDER BY id")
    with connect() as con:
        return {(r["item_type"], r["item_id"]): dict(r) for r in con.execute(sql, (isin, *item_types))}
