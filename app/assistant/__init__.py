"""Assistant IA – propriétaire : Alfred.

Flux : faits réels -> LLM -> garde-fou (nombres + vocabulaire) -> sinon template.
L'API ne plante jamais à cause du LLM.
"""
from __future__ import annotations

import json
import re

from app.assistant import guard, llm, prompts, templates
from app.assistant.facts import impact_facts, preview_facts, report_facts


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


def summarize_event_preview(preview: dict) -> str:
    """Réactions passées du trading au type d'annonce ; LLM vérifié par le garde-fou, sinon template."""
    return _generate(prompts.PREVIEW_USER, preview_facts(preview), templates.preview_summary(preview), max_tokens=220)


_BULLET = re.compile(r"^\s*(?:[-•*]|\d+[.)])\s+")
_WHO_ALL = re.compile(r"\b(investors?|institutional|retail)\b", re.I)


def _points(topic: str, facts: dict, fallback: list[str]) -> list[str]:
    """3–4 points courts : LLM, chaque point vérifié par le garde-fou ; sinon les points du template."""
    text = llm.complete(prompts.SYSTEM, prompts.POINTS_USER.format(
        topic=topic, facts=json.dumps(facts, ensure_ascii=False, indent=2)), 260)
    if text:
        raw = text.replace(" - ", "\n- ") if "\n" not in text else text
        pts = [_BULLET.sub("", line).strip() for line in raw.splitlines() if _BULLET.match(line)]
        if 3 <= len(pts) <= 4 and all(guard.check(p, facts) and not _WHO_ALL.search(p) for p in pts):
            return pts
    return fallback


def points_impact_card(card: dict) -> list[str]:
    return _points("how the stock traded on this day versus its normal state", impact_facts(card), templates.impact_points(card))


def points_event_preview(preview: dict) -> list[str]:
    return _points("how the stock's trading reacted to PAST releases of this type", preview_facts(preview),
                   templates.preview_points(preview))


def points_report(report: dict) -> list[str]:
    return _points("the trading profile of the period", report_facts(report), templates.report_points(report))


__all__ = ["summarize_impact_card", "summarize_report", "summarize_event_preview",
           "points_impact_card", "points_event_preview", "points_report"]
