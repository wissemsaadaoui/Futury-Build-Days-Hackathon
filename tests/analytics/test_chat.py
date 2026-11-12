"""Chat libre de l'AI Assistant (app/assistant/chat.py) : outils, garde-fou, repli template, route."""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app import config, etl
from app.assistant import chat as C
from app.assistant import guard

PBB = "DE0008019001"
pytestmark = pytest.mark.skipif(etl.load_xlm().empty, reason="data/raw/spreads absent")


def ask(question: str, history: list[dict] | None = None) -> dict:
    return C.chat(PBB, [*(history or []), {"role": "user", "content": question}])


@pytest.fixture()
def no_llm(monkeypatch):
    monkeypatch.setattr(C.llm, "is_configured", lambda: False)


# ---------- Fake Anthropic client ----------
def _text(t: str):
    return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=t)])


def _tool(name: str, args: dict, id_: str = "t1"):
    return SimpleNamespace(stop_reason="tool_use", content=[SimpleNamespace(type="tool_use", id=id_, name=name, input=args)])


@pytest.fixture()
def fake_llm(monkeypatch):
    """Rejoue une liste de réponses ; garde les requêtes envoyées."""
    state = {"responses": [], "requests": []}

    class Messages:
        def create(self, **kw):
            state["requests"].append(kw)
            return state["responses"].pop(0)

    monkeypatch.setattr(C.llm, "is_configured", lambda: True)
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(C, "_client", lambda: SimpleNamespace(messages=Messages()))
    return state


# ---------- Dates relatives ----------
def test_context_uses_latest_data_not_today():
    ctx = C.context()
    assert ctx["latest_data_day"] == "2026-10-30"
    assert ctx["latest_week"] == {"from": "2026-10-26", "to": "2026-10-30", "label": "26–30 Oct 2026"}
    assert ctx["latest_month"]["label"] == "1–30 Oct 2026"


def test_this_week_fallback_uses_tool_numbers(no_llm):
    r = ask("What happened this week?")
    assert r["as_of"] == "2026-10-30"
    assert "Latest data: 26–30 Oct 2026." in r["answer"]
    res = C.run_tool(PBB, "get_period_summary", {"from": "2026-10-26", "to": "2026-10-30"})
    assert guard.check(r["answer"], {"context": C.context(), "tool_results": [C.public(res)]})
    assert f"{res['volume_shares']['period_avg']:,} shares" in r["answer"]
    assert 3 <= len(C._sentences(r["answer"])) <= 5


@pytest.mark.parametrize(
    "question,tool",
    [
        ("What happened in the latest week?", "get_period_summary"),
        ("Why was 29 Sep unusual?", "get_day"),
        ("What to expect from today's Q3 release?", "get_event_preview"),
        ("How does pbb compare with its peers?", "get_peer_comparison"),
        ("How was liquidity last month?", "get_period_summary"),
    ],
)
def test_router_picks_the_right_tool(question, tool):
    assert C.route(PBB, question)[0] == tool


def test_parse_date_variants():
    assert C.parse_date("Why was 29 Sep unusual?") == "2026-09-29"
    assert C.parse_date("what about September 29th") == "2026-09-29"
    assert C.parse_date("on 2026-08-13 please") == "2026-08-13"
    assert C.parse_date("this week") is None


def test_suggested_questions_answer_with_links(no_llm):
    day = ask("Why was 29 Sep unusual?")
    assert day["links"] == [{"label": "Day view 29 Sep 2026", "type": "day", "ref": "2026-09-29"}]
    assert "Spread 1.2x" in day["answer"]
    prev = ask("What to expect from today's Q3 release?")
    assert prev["links"][0]["type"] == "preview" and "12 Nov 2026" in prev["answer"]
    assert "+11.7%" in prev["answer"]
    peers = ask("How does pbb compare with its peers?")
    assert peers["links"][0]["type"] == "compare" and "6 peers" in peers["answer"]


# ---------- Hors périmètre / prédiction ----------
@pytest.mark.parametrize(
    "question",
    ["Will the share price rise after Q3?", "Should I buy pbb now?", "What is the price target for next month?"],
)
def test_prediction_or_advice_is_refused(no_llm, question):
    r = ask(question)
    assert r["answer"].startswith(C.PAST_ONLY) and r["reason"] in ("prediction", "advice")
    assert [link["type"] for link in r["links"]] == ["question", "question"]
    assert not _DATA_FIGURE.search(r["answer"])  # texte fixe (« does not forecast prices ») : pas de chiffres


def test_llm_prediction_is_rejected_by_guard(fake_llm):
    # pré-filtre : la question de prédiction n'atteint même pas le LLM
    fake_llm["responses"] = [_text("The share price will rise after the Q3 release.")]
    r = ask("Will the share price rise after Q3?")
    assert r["reason"] == "prediction" and fake_llm["requests"] == []


# ---------- Repli template ----------
def test_llm_unavailable_falls_back_to_template(no_llm):
    r = ask("What happened in the latest week?")
    res = C.run_tool(PBB, "get_period_summary", {"from": "2026-10-26", "to": "2026-10-30"})
    assert r["answer"] == C.template_answer("get_period_summary", res, C.context())


def test_llm_error_falls_back(fake_llm):
    fake_llm["responses"] = []  # pop sur liste vide -> exception dans le client
    r = ask("What happened in the latest week?")
    assert "Latest data: 26–30 Oct 2026." in r["answer"]


# ---------- Tool use ----------
def test_llm_tool_use_answer_is_kept_when_grounded(fake_llm):
    res = C.public(C.run_tool(PBB, "get_period_summary", {"from": "2026-10-26", "to": "2026-10-30"}))
    sp = res["spread_bps_25k_eur"]
    text = (f"In the latest week (26–30 Oct 2026) the average spread was {sp['period_avg']:.1f} bps versus "
            f"{sp['baseline_avg']:.1f} bps before. Latest data: 26–30 Oct 2026.")
    fake_llm["responses"] = [_tool("get_period_summary", {"from": "2026-10-26", "to": "2026-10-30"}), _text(text)]
    r = ask("What happened this week?")
    assert r["answer"] == text
    req = fake_llm["requests"][0]
    assert req["thinking"] == {"type": "disabled"} and "temperature" not in req
    assert "2026-10-30" in req["system"] and {t["name"] for t in req["tools"]} >= {"get_day", "get_period_summary"}
    sent = fake_llm["requests"][1]["messages"][-1]["content"][0]
    assert sent["type"] == "tool_result" and "NaN" not in sent["content"] and "_card" not in sent["content"]


def test_llm_invented_number_falls_back(fake_llm):
    fake_llm["responses"] = [
        _tool("get_period_summary", {"from": "2026-10-26", "to": "2026-10-30"}),
        _text("The average spread was 12345.6 bps this week. Latest data: 26–30 Oct 2026."),
    ]
    r = ask("What happened this week?")
    assert "12345.6" not in r["answer"] and "Latest data: 26–30 Oct 2026." in r["answer"]


def test_llm_forbidden_words_fall_back(fake_llm):
    res = C.public(C.run_tool(PBB, "get_period_summary", {"from": "2026-10-26", "to": "2026-10-30"}))
    fake_llm["responses"] = [
        _tool("get_period_summary", {"from": "2026-10-26", "to": "2026-10-30"}),
        _text(f"Institutional investors pushed the spread to {res['spread_bps_25k_eur']['period_avg']:.1f} bps."),
    ]
    assert "nstitutional" not in ask("What happened this week?")["answer"]


def test_max_four_tool_rounds(fake_llm):
    fake_llm["responses"] = [_tool("list_events", {}, f"t{i}") for i in range(6)]
    r = ask("What happened in the latest week?")
    assert len(fake_llm["requests"]) == C.MAX_TOOL_ROUNDS + 1
    assert "Latest data" in r["answer"]  # repli template


def test_history_is_limited_and_starts_with_user(fake_llm):
    hist = []
    for i in range(5):
        hist += [{"role": "user", "content": f"q{i}"}, {"role": "assistant", "content": f"a{i}"}]
    fake_llm["responses"] = [_text("This tool only describes past Xetra trading.")]
    ask("How was liquidity?", hist)
    msgs = fake_llm["requests"][0]["messages"]
    assert len(msgs) <= C.MAX_HISTORY and msgs[0]["role"] == "user"


def test_tool_errors_never_raise():
    assert "error" in C.run_tool(PBB, "get_day", {"date": "2026-11-12"})
    assert "error" in C.run_tool(PBB, "get_impact_card", {"event_id": "evt_999"})
    assert "error" in C.run_tool(PBB, "nope", {})


# ---------- Route ----------
def test_route_auth_schema_and_rate_limit(no_llm):
    from fastapi.testclient import TestClient

    from app.api import assistant as route
    from app.main import app
    from tests.helpers import logged_in_client

    body = {"isin": PBB, "messages": [{"role": "user", "content": "Why was 29 Sep unusual?"}]}
    assert TestClient(app).post("/assistant/chat", json=body).status_code == 401
    client = logged_in_client()
    route._calls.clear()
    r = client.post("/assistant/chat", json=body)
    assert r.status_code == 200
    assert set(r.json()) == {"answer", "links", "as_of"} and r.json()["links"][0]["type"] == "day"
    assert client.post("/assistant/chat", json={**body, "isin": "XX0000000000"}).status_code == 404
    assert client.post("/assistant/chat", json={"isin": PBB, "messages": []}).status_code == 422
    route._calls.clear()
    for _ in range(route.RATE_LIMIT):
        route._check_rate("Bearer x", now=0.0)
    with pytest.raises(Exception) as exc:
        route._check_rate("Bearer x", now=1.0)
    assert getattr(exc.value, "status_code", None) == 429
    route._check_rate("Bearer x", now=61.0)  # fenêtre glissante : de nouveau autorisé
    route._calls.clear()


# ---------- Périmètre du chat (alfred/chat-scope) ----------
_DATA_FIGURE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|bps|x\b|×|shares|EUR|sessions?)|EUR\s*\d|\d{1,3}(?:,\d{3})+")

OFF_TOPIC_CASES = [
    ("What is the weather in Frankfurt tomorrow?", "off_topic"),
    ("Write me a poem about covered bonds", "off_topic"),
    ("Who is the CEO of pbb?", "external_info"),
    ("What did the ECB announce about interest rates?", "external_info"),
    ("Should I buy or sell pbb shares now?", "advice"),
    ("What will the price of pbb be next week?", "prediction"),
    ("How did Tesla shares trade last week?", "off_topic"),
    ("   ", "off_topic"),
]


@pytest.mark.parametrize("question,reason", OFF_TOPIC_CASES)
def test_off_topic_questions_get_no_data(no_llm, question, reason):
    r = ask(question)
    assert r["reason"] == reason
    assert not _DATA_FIGURE.search(r["answer"]), r["answer"]
    assert len(r["links"]) == 2 and all(l["type"] == "question" and l["ref"] == l["label"] for l in r["links"])
    assert all(l["ref"] in C.SUGGESTED_QUESTIONS for l in r["links"])
    lead = C.PAST_ONLY if reason in ("prediction", "advice") else "I can only answer questions about pbb's"
    assert r["answer"].startswith(lead)


@pytest.mark.parametrize("question", C.SUGGESTED_QUESTIONS)
def test_demo_questions_still_answer_with_figures(no_llm, question):
    r = ask(question)
    assert r["reason"] is None and _DATA_FIGURE.search(r["answer"]) and r["links"]
    assert r["links"][0]["type"] in ("day", "event", "preview", "compare")


@pytest.mark.parametrize("question,reason", [
    ("Sollte ich pbb-Aktien kaufen?", "advice"),
    ("Est-ce que je dois acheter pbb ?", "advice"),
    ("Was ist die Prognose für den Kurs?", "prediction"),
    ("Quelle est la prévision du cours la semaine prochaine ?", "prediction"),
])
def test_prefilter_french_german(question, reason):
    assert C.prefilter(question) == reason


def test_trading_vocabulary_is_not_advice():
    assert C.prefilter("Was there net buying in the latest week?") is None
    assert C.prefilter("How many buy-initiated sweeps were flagged?") is None
    assert C.route(PBB, "Write me a poem") is None  # jamais de route « par défaut »


def test_prefilter_answers_without_calling_the_llm(fake_llm):
    r = ask("Should I buy pbb?")
    assert r["reason"] == "advice" and fake_llm["requests"] == []


def test_llm_decline_tool_is_respected(fake_llm):
    fake_llm["responses"] = [_tool("decline", {"reason": "external_info", "suggestion": "Ask about liquidity"})]
    r = ask("What does pbb's management think about the market?")
    assert r["reason"] == "external_info" and not _DATA_FIGURE.search(r["answer"])
    assert len(fake_llm["requests"]) == 1  # aucun outil de données exécuté après decline
    assert any(t["name"] == "decline" for t in fake_llm["requests"][0]["tools"])
    assert "decline" in fake_llm["requests"][0]["system"]


def test_llm_answer_without_tools_is_not_trusted(fake_llm):
    fake_llm["responses"] = [_text("The spread was 42.0 bps on average.")]
    r = ask("How was liquidity?")
    assert r["reason"] == "off_topic" and "42.0" not in r["answer"]


def test_auction_wording():
    from app.assistant import prompts

    assert not C.answer_ok("Auctions were 13.6% share of executions.", {"x": 13.6})
    assert "auction share of volume" in prompts.CHAT_SYSTEM and "share of executions" in prompts.CHAT_SYSTEM
