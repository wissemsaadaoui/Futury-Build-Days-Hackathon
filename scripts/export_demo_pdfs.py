"""Pré-génère les PDF de la démo pbb (scénario de PROJECT.md §6), via l'API (mêmes routes que le bouton « Export »).

Lancer depuis la racine du repo :
    python -m scripts.export_demo_pdfs                  # -> exports/demo/
    python -m scripts.export_demo_pdfs --out /tmp/pdfs
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.main import app

PBB = "DE0008019001"
DEMO_PDFS = [
    "/events/evt_002/impact-card.pdf",  # b) 13.02 ad hoc : impact card + intraday
    f"/days/{PBB}/2026-02-12/impact-card.pdf",  # c) veille, sans annonce
    f"/days/{PBB}/2026-03-18/impact-card.pdf",  # d) directors' dealings / droits de vote
    f"/days/{PBB}/2026-08-31/impact-card.pdf",  # e) closing auction = 94 % du volume
    f"/days/{PBB}/2026-09-29/impact-card.pdf",  # f) rupture du spread sans annonce
    f"/stocks/{PBB}/report.pdf?from=2026-01-01&to=2026-10-30",  # report pbb janv.–oct.
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=config.ROOT / "exports" / "demo", help="dossier de sortie")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    with TestClient(app) as client:  # démarre l'app (chargement des données) sans lancer de serveur
        for url in DEMO_PDFS:
            r = client.get(url)
            if r.status_code != 200:
                print(f"ERREUR {r.status_code}  {url}  {r.text[:200]}")
                continue
            name = re.search(r'filename="([^"]+)"', r.headers["content-disposition"]).group(1)
            (args.out / name).write_bytes(r.content)
            print(f"{len(r.content):>8,} B  {args.out / name}")
    print(f"Durée : {time.perf_counter() - start:.1f} s")


if __name__ == "__main__":
    main()
