"""Accès aux données préparées pour l'analyse (au-dessus de app.etl)."""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from app import config, etl


def has_ohlc() -> bool:
    return not etl.load_ohlc().empty


def has_flows() -> bool:
    return not etl.load_flows().empty


@lru_cache(maxsize=1)
def trading_days() -> pd.DatetimeIndex:
    """Calendrier de trading = toutes les dates présentes dans les données."""
    dates = [etl.load_xlm()["date"]]
    if has_ohlc():
        dates.append(pd.to_datetime(etl.load_ohlc()["date"]))
    s = pd.concat(dates)
    return pd.DatetimeIndex(sorted(pd.to_datetime(s).unique()))


# ---------- accès rapide par ISIN ----------
# Positions des lignes de chaque ISIN dans les grands tableaux ETL, calculées une fois (groupby().indices) :
# évite une comparaison de chaînes sur 0,5 à 2,6 M lignes à chaque appel (peers en base index : ~120 ISIN).
# Les positions sont croissantes : df.take(pos) garde l'ordre d'origine, comme un filtre booléen.
def _load(name: str) -> pd.DataFrame:
    return getattr(etl, f"load_{name}")()  # résolu à chaque appel (les tests remplacent etl.load_*)


@lru_cache(maxsize=3)
def _positions(name: str) -> dict:
    df = _load(name)
    if df.empty:
        return {}
    return {str(k): v for k, v in df.groupby(df["isin"].astype(str), observed=True, sort=False).indices.items()}


def _rows(name: str, isin: str) -> pd.DataFrame:
    df = _load(name)
    pos = _positions(name).get(isin)
    return df.iloc[0:0] if pos is None else df.take(pos)


def known_isin(isin: str) -> bool:
    return isin in _positions("xlm") or (has_ohlc() and isin in _positions("ohlc"))


@lru_cache(maxsize=256)
def spread_series(isin: str, notional: float = config.REF_NOTIONAL) -> pd.Series:
    """Impact_bps au notional de référence, indexé par date."""
    x = _rows("xlm", isin)
    s = x[x["notional"] == notional].set_index("date")["impact_bps"]
    return s.sort_index()


@lru_cache(maxsize=256)
def index_series(isin: str) -> pd.Series:
    x = _rows("xlm", isin)
    return x.drop_duplicates("date").set_index("date")["index"].sort_index()


def index_on(isin: str, day: pd.Timestamp) -> str | None:
    s = index_series(isin)
    s = s[s.index <= day]
    return None if s.empty else str(s.iloc[-1])


# ---------- peers ----------
# « manual » : liste choisie à la main (config.PEERS, ex. pbb) ; « index » : les autres membres du même indice
# À LA DATE (colonne Index du XLM), pour tout émetteur sans liste manuelle. Une médiane « peers » d'un jour donné
# ne prend que les peers valides ce jour-là (mask_peer) : un émetteur passé du SDAX au MDAX change de peers ce jour-là.
def peer_basis(isin: str) -> str:
    return "manual" if config.PEERS.get(isin) else "index"


@lru_cache(maxsize=1)
def _index_wide() -> pd.DataFrame:
    """Indice de chaque action par jour (lignes = dates, colonnes = ISIN, NaN = hors des indices ce jour-là)."""
    x = etl.load_xlm()
    if x.empty:
        return pd.DataFrame()
    x = x.drop_duplicates(["date", "isin"])
    return x.pivot(index="date", columns="isin", values="index").sort_index()


@lru_cache(maxsize=256)
def peer_membership(isin: str) -> pd.DataFrame:
    """Booléens (dates × peers) : True si le peer compte pour l'émetteur ce jour-là. Base manual : toujours True."""
    if peer_basis(isin) == "manual":
        peers = [p for p in config.PEERS.get(isin, []) if p != isin]
        return pd.DataFrame(True, index=trading_days(), columns=peers)
    w = _index_wide()
    if w.empty or isin not in w.columns:
        return pd.DataFrame(index=trading_days())
    own = w[isin]
    same = w.drop(columns=[isin]).eq(own, axis=0) & own.notna().to_numpy()[:, None]
    same = same.loc[:, same.any()]
    return same.reindex(trading_days(), fill_value=False)


def peers_of(isin: str) -> list[str]:
    """Tous les peers de l'émetteur sur la période des données (base index : membres du même indice au moins un jour)."""
    return list(peer_membership(isin).columns)


def peers_on(isin: str, day: pd.Timestamp) -> list[str]:
    """Peers valides ce jour-là."""
    m = peer_membership(isin)
    day = pd.Timestamp(day)
    if day not in m.index:
        return [] if peer_basis(isin) == "index" else list(m.columns)
    row = m.loc[day]
    return list(row[row].index)


def mask_peer(isin: str, peer: str, s: pd.Series) -> pd.Series:
    """Série du peer limitée aux jours où il compte comme peer (base manual : inchangée)."""
    if peer_basis(isin) == "manual" or s.empty:
        return s
    m = peer_membership(isin)
    if peer not in m.columns:
        return s.iloc[0:0]
    keep = m[peer].reindex(s.index, fill_value=False)
    return s[keep.to_numpy()]


def n_peers(isin: str, day: pd.Timestamp | None = None) -> int:
    """Nombre de peers (base index : le jour donné, sinon la dernière séance)."""
    if peer_basis(isin) == "manual":
        return len(peers_of(isin))
    return len(peers_on(isin, day if day is not None else trading_days()[-1]))


# ---------- noms ----------
_LEGAL = {"AG": "AG", "SE": "SE", "KGAA": "KGaA", "GMBH": "GmbH", "NV": "NV", "PLC": "PLC", "S.A.": "S.A.", "REIT": "REIT",
          "CO.": "Co.", "CO": "Co.", "HLDG": "Hldg", "GRP": "Group"}
_SUFFIXES = ("INH O.N.", "INH O.N", "INH. O.N.", "NA O.N.", "O.N.VZO", "VZO NA O.N.", "VZO O.N.", "VNA O.N.", "NA ON",
             "INH ON", "O.N.", "O.N", "ON", "VZO", "ST", "INH.", "INH", "NA", "EO 1", "EO-,01", "EO -,01", "EO-,10", "ORD.", "A")
_KEEP_UPPER = {"BASF", "KION", "LPKF", "SFC", "TKMS", "1+1", "AUTO1", "IONOS", "SUSS", "LEG", "TAG", "STO"}


def _tidy_name(raw: str) -> str:
    """« SUSS MICROTEC SE NA O.N. » -> « SUSS Microtec SE » (nom d'instrument Xetra sans catégorie d'action)."""
    name = str(raw).upper().replace("+CO.", " & CO. ").replace(" + CO.", " & CO. ")
    name = " ".join(name.replace(".O.N.", " O.N.").replace(".EO-", " EO-").replace(".INH", " INH").split())
    changed = True
    while changed:
        changed = False
        for suf in _SUFFIXES:
            if name.endswith(" " + suf):
                name, changed = name[: -len(suf) - 1].rstrip(), True
    if any(c.islower() for c in str(raw)):  # déjà en casse normale (config.NAMES, ex. « GRENKE AG »)
        return str(raw)

    def cap(w: str) -> str:
        return "+".join("-".join(x[:1] + x[1:].lower() for x in y.split("-")) for y in w.split("+"))

    def word(w: str) -> str:
        if w in _LEGAL or w in _KEEP_UPPER:
            return _LEGAL.get(w, w)
        if "." in w.strip("."):  # abréviations Xetra (« DT.TELEKOM », « FRESEN.MED.CARE ») : casse titre partout
            return ".".join(_LEGAL.get(x, cap(x)) for x in w.split("."))
        if len(w.strip(".")) <= 3 or any(ch.isdigit() for ch in w) or ("+" in w and len(w) <= 5):
            return w
        return cap(w)

    return " ".join(word(w) for w in name.split())


@lru_cache(maxsize=1)
def _universe_names() -> dict[str, tuple[str, str]]:
    u = etl.get_universe()
    return {r.isin: (r.name, r.mnemonic) for r in u.itertuples()} if not u.empty else {}


def name_of(isin: str) -> str:
    if isin in config.NAMES:
        return config.NAMES[isin]
    if isin in _universe_names():
        return _tidy_name(_universe_names()[isin][0])
    x = etl.load_xlm()
    m = x.loc[x["isin"] == isin, "mnemonic"]
    return str(m.iloc[0]) if not m.empty else isin


def mnemonic_of(isin: str) -> str | None:
    if isin in _universe_names():
        return str(_universe_names()[isin][1])
    x = etl.load_xlm()
    m = x.loc[x["isin"] == isin, "mnemonic"]
    return str(m.iloc[0]) if not m.empty else None


# Nom court dans les phrases (marque) : « pbb » ; sinon le nom d'affichage
SHORT_NAMES = {"DE0008019001": "pbb"}


def short_name(isin: str) -> str:
    return SHORT_NAMES.get(isin) or name_of(isin)


# ---------- couverture ----------
MIN_SESSIONS = config.BASELINE_DAYS + 1  # 20 séances de baseline + le jour mesuré


def spread_sessions(isin: str) -> int:
    """Séances avec un spread XLM (25 000 €) mesuré ; NaN (carnet trop mince) ne compte pas."""
    return int(spread_series(isin).notna().sum())


def require_sessions(isin: str) -> None:
    """Lève InsufficientData (404, message clair) si l'émetteur a trop peu de séances pour une baseline 20 jours."""
    n = spread_sessions(isin)
    if n < MIN_SESSIONS:
        from app.analytics.impact import InsufficientData

        raise InsufficientData(
            f"Not enough Xetra data for {name_of(isin)} ({isin}): {n} session(s) with a measured spread "
            f"in the files, at least {MIN_SESSIONS} are needed (20-day baseline + the measured day)."
        )


def has_events(isin: str) -> bool:
    ev = etl.load_events()
    return bool((ev["isin"] == isin).any()) if not ev.empty else False


@lru_cache(maxsize=256)
def ohlc(isin: str) -> pd.DataFrame:
    """OHLC d'une action, indexé par date (vide si pas de données)."""
    df = etl.load_ohlc()
    if df.empty:
        return df
    d = _rows("ohlc", isin).copy()
    d["date"] = pd.to_datetime(d["date"])
    return d.set_index("date").sort_index()


@lru_cache(maxsize=256)
def flows(isin: str) -> pd.DataFrame:
    """Flows JOURNALIERS d'une action : uniquement les lignes n_days == 1.
    Une ligne multi-jours (n_days > 1, flux censuré publié plus tard) mélangerait plusieurs séances :
    elle est exclue de toutes les métriques journalières (auction_share, net flow, by_participant)."""
    df = etl.load_flows()
    if df.empty:
        return df
    d = _rows("flows", isin).copy()
    if "n_days" in d.columns:
        d = d[d["n_days"].fillna(1).astype(int) == 1]
    d["date"] = pd.to_datetime(d["date"])
    for col in ("participant", "mode", "side"):
        d[col] = d[col].astype(str)
    return d


# ---------- trades (on-book Xetra) ----------
SESSION_OPEN = "09:00"
SESSION_CLOSE = "17:30"   # fin du continu ; la closing auction suit (~17:30–17:35)
SESSION_END = "17:36"     # après : impressions hors séance (exclues)


@lru_cache(maxsize=64)
def trades(isin: str) -> pd.DataFrame:
    """Trades on-book d'une action pendant la séance Xetra (09:00–17:36, enchères comprises).
    Les impressions avant 09:00 ou après 17:36 (hors séance, sans agresseur) sont exclues, SAUF les enchères
    identifiées (opening/midday/closing) : une closing auction prolongée peut se terminer après 17:36."""
    t = etl.load_trades(isin)
    if t.empty:
        return t
    hm = t["ts_local"].dt.strftime("%H:%M")
    labelled = t["auction_type"].fillna("").astype(str) != ""
    t = t[((hm >= SESSION_OPEN) & (hm < SESSION_END)) | labelled].copy()
    t["side"] = t["side"].fillna("").astype(str)
    t["auction_type"] = t["auction_type"].fillna("").astype(str)
    return t.reset_index(drop=True)


def has_trades(isin: str) -> bool:
    return not trades(isin).empty


@lru_cache(maxsize=64)
def continuous_trades(isin: str) -> pd.DataFrame:
    """Exécutions du trading continu avec un côté agresseur connu (BUY|SELL), hors enchères."""
    t = trades(isin)
    if t.empty:
        return t
    hm = t["ts_local"].dt.strftime("%H:%M")
    keep = t["side"].isin(["BUY", "SELL"]) & (t["auction_type"] == "") & (hm < SESSION_CLOSE)
    return t[keep].reset_index(drop=True)


@lru_cache(maxsize=256)
def auction_volume_series(isin: str, kind: str) -> pd.Series:
    """Volume (actions) de l'enchère `kind` (opening|midday|closing) par jour de trading.
    0 si l'enchère n'a rien exécuté ce jour-là (jours présents dans les trades)."""
    t = trades(isin)
    if t.empty:
        return pd.Series(dtype=float)
    days = pd.DatetimeIndex(sorted(t["date"].unique()))
    v = t[t["auction_type"] == kind].groupby("date")["qty"].sum().astype(float)
    return v.reindex(days, fill_value=0.0)


@lru_cache(maxsize=256)
def closing_auction_share_series(isin: str) -> pd.Series:
    """Part du volume du jour exécutée dans la closing auction (0–1) : volume closing (trades) ÷ volume OHLC."""
    px = ohlc(isin)
    ca = auction_volume_series(isin, "closing")
    if px.empty or ca.empty:
        return pd.Series(dtype=float)
    vol = px["volume"].astype(float).reindex(ca.index)
    return (ca / vol.where(vol > 0)).dropna()


@lru_cache(maxsize=256)
def adtv_series(isin: str, n: int = config.ALERT_ADTV_DAYS) -> pd.Series:
    """ADTV en € : moyenne du turnover_eur (OHLC) des n jours de trading PRÉCÉDENTS (jour courant exclu)."""
    px = ohlc(isin)
    if px.empty:
        return pd.Series(dtype=float)
    t = px["turnover_eur"].astype(float)
    return t.rolling(n, min_periods=max(5, n // 3)).mean().shift(1)


@lru_cache(maxsize=256)
def auction_share_series(isin: str) -> pd.Series:
    """Part du volume exécutée en AUCTION, par jour (0–1)."""
    f = flows(isin)
    if f.empty:
        return pd.Series(dtype=float)
    tot = f.groupby("date")["volume"].sum()
    auc = f[f["mode"] == "AUCTION"].groupby("date")["volume"].sum()
    return (auc.reindex(tot.index).fillna(0) / tot).sort_index()


def stock_ref(isin: str, day: pd.Timestamp | None = None) -> dict:
    idx = index_on(isin, day) if day is not None else index_on(isin, trading_days()[-1])
    return {
        "isin": isin,
        "name": name_of(isin),
        "index": idx or "",
        "sector": config.SECTORS.get(isin, ""),
    }


def clear_caches() -> None:
    """À appeler si les données ETL changent (tests)."""
    for fn in (trading_days, spread_series, index_series, ohlc, flows, auction_share_series, trades, continuous_trades,
               auction_volume_series, closing_auction_share_series, adtv_series, _index_wide, peer_membership, _positions,
               _universe_names):
        fn.cache_clear()
    from app.analytics import dashboard, universe  # imports tardifs (ils dépendent de data)

    universe._list_stocks.cache_clear()
    dashboard._peer_spread_median.cache_clear()
    from app.analytics import pricing  # import tardif (pricing dépend de data)

    pricing.clear_caches()
    from app.analytics import alerts

    alerts.clear_caches()
