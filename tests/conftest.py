"""Configuration commune des tests : valeurs de TEST pour le login (avant tout import de app.config).

load_dotenv() ne remplace pas une variable déjà définie : ces valeurs priment sur un éventuel .env local.
"""
from __future__ import annotations

import os

os.environ["APP_PASSWORD"] = "test-password"  # valeur de test uniquement
os.environ["SESSION_SECRET"] = "test-session-secret"
