"""Assistant IA – propriétaire : Alfred.

Flux : faits réels -> LLM -> garde-fou (nombres + vocabulaire) -> sinon template.
L'API ne plante jamais à cause du LLM.
"""
from __future__ import annotations

import json
import re

from app.assistant import guard, llm, prompts, templates
from app.assistant.facts import impact_facts, report_facts


# Les données décrivent des exécutions, pas des investisseurs (en plus du garde-fou, inchangé)
_WHO = re.compile(r"\binvestors?\b", re.I)


def _generate(user_tpl: str, facts: dict, fallback: str, max_tokens: int = 400) -> str:
    text = llm.complete(prompts.SYSTEM, user_tpl.format(facts=json.dumps(facts, ensure_ascii=False, indent=2)), max_tokens)
    if text and guard.check(text, facts) and not _WHO.search(text):
        return text
    return fallback


def summarize_impact_card(card: dict) -> str:
    return _generate(prompts.IMPACT_USER, impact_facts(card), templates.impact_summary(card))


def summarize_report(report: dict) -> str:
    return _generate(prompts.REPORT_USER, report_facts(report), templates.report_headline(report), max_tokens=120)


__all__ = ["summarize_impact_card", "summarize_report"]
