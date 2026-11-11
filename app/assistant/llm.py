"""Client LLM minimal. Renvoie None en cas de problème : l'appelant utilise alors le template."""
from __future__ import annotations

import logging

from app import config

log = logging.getLogger(__name__)

DEFAULT_MODELS = {
    "anthropic": "claude-haiku-5-5",
    "openai": "gpt-4o-mini",  # à ajuster selon le modèle disponible sur votre compte
}


def is_configured() -> bool:
    return config.LLM_PROVIDER in DEFAULT_MODELS and bool(config.LLM_API_KEY)


def complete(system: str, user: str, max_tokens: int = 400) -> str | None:
    if not is_configured():
        return None
    model = config.LLM_MODEL or DEFAULT_MODELS[config.LLM_PROVIDER]
    try:
        if config.LLM_PROVIDER == "anthropic":
            import anthropic

            client = anthropic.Anthropic(api_key=config.LLM_API_KEY, timeout=config.LLM_TIMEOUT_S)
            msg = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0.2,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        else:
            from openai import OpenAI

            client = OpenAI(api_key=config.LLM_API_KEY, timeout=config.LLM_TIMEOUT_S)
            resp = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0.2,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            text = resp.choices[0].message.content or ""
        text = " ".join(text.split())
        return text or None
    except Exception as exc:  # réseau, quota, clé invalide, SDK absent…
        log.warning("LLM call failed (%s): %s", config.LLM_PROVIDER, exc)
        return None
