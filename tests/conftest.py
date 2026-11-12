"""Configuration commune des tests : valeurs de TEST pour le login (avant tout import de app.config).

load_dotenv() ne remplace pas une variable déjà définie : ces valeurs priment sur un éventuel .env local.
"""
from __future__ import annotations

import os
import tempfile

os.environ["APP_PASSWORD"] = "test-password"  # valeur de test uniquement
os.environ["SESSION_SECRET"] = "test-session-secret"
# Journal des décisions / seuils : base SQLite temporaire, jamais data/decisions.db
os.environ["DECISIONS_DB"] = os.path.join(tempfile.mkdtemp(prefix="iih-tests-"), "decisions.db")
