"""Intent classifier (decision 29): the plain-Python predict matches scikit-learn, and the graph
uses it in code (prompt hint for complaints and retention, intent in the case and the log)."""

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, SystemMessage

from app.agent import graph as graph_module
from app.agent import intent
from app.agent.intent import Intent, get_intent_model
from app.sessions import get_session_store
from tests.test_account_tools import ToolCallingFake
from tests.test_agent import RecordingFake, collect
from tests.test_handoff import cases, handoff_call, say  # noqa: F401 (fixture)

PARITY = json.loads((Path(__file__).parent / "fixtures/intent_parity.json").read_text("utf-8"))


@pytest.mark.parametrize("sample", PARITY, ids=range(len(PARITY)))
def test_plain_python_predict_matches_scikit_learn(sample):
    got = get_intent_model().predict_proba(sample["text"])
    assert got.keys() == sample["proba"].keys()
    for label, p in sample["proba"].items():
        assert got[label] == pytest.approx(p, abs=1e-9)


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("¿Cuál es el saldo de mi cuenta?", "transactional"),
        ("Qual é o saldo da minha conta?", "transactional"),
        ("Me cobraron dos veces y nadie me responde, quiero reclamar", "complaint"),
        ("Quero cancelar meu cartão, vou mudar de banco", "retention"),
        ("no puedo entrar a la app, me da error", "technical"),
        ("gracias", "other"),
    ],
)
def test_classifies_clear_messages(text, label):
    seen = intent.classify(text)
    assert seen.label == label
    assert (seen.reason_category is None) == (label == "other")


def test_complaint_carries_the_banks_first_contact_resolution_rate():
    seen = intent.classify("Quiero poner una queja, me cobraron una comisión indebida")
    assert seen.label == "complaint" and seen.confident and seen.early_handoff
    assert seen.reason_category == "Queja" and seen.fcr_rate == pytest.approx(0.4339)


def test_small_talk_and_unsure_messages_keep_the_conversation_intent():
    complaint = Intent("complaint", 0.9, "Queja", 0.43, confident=True).as_dict()
    thanks = Intent("other", 0.95, None, None, confident=True)
    unsure = Intent("product", 0.3, "Producto", 0.89, confident=False)
    product = Intent("product", 0.8, "Producto", 0.89, confident=True)
    assert intent.update(complaint, thanks) == complaint
    assert intent.update(complaint, unsure) == complaint
    assert intent.update(complaint, product)["label"] == "product"


def test_hint_only_for_confident_low_resolution_intents():
    assert intent.hint(Intent("complaint", 0.9, "Queja", 0.4339, True), "es").count("43%") == 1
    assert "atendente humano" in intent.hint(Intent("retention", 0.9, "Retención", 0.6, True), "pt")
    assert intent.hint(Intent("complaint", 0.4, "Queja", 0.4339, False), "es") is None
    assert intent.hint(Intent("transactional", 0.9, "Transaccional", 0.9, True), "es") is None


async def test_graph_adds_the_hint_and_keeps_the_intent_in_the_session():
    model = RecordingFake(messages=iter([AIMessage("Lo siento."), AIMessage("De nada.")]), calls=[])
    graph = graph_module.build_graph(model)
    await collect(graph, "s-intent", "Estoy harto, quiero presentar un reclamo formal", "es")
    await collect(graph, "s-intent", "gracias", "es")

    first, second = model.calls
    base = graph_module.system_prompt("es")
    assert isinstance(first[0], SystemMessage) and first[0].content.startswith(base)
    assert "43%" in first[0].content.removeprefix(base)
    assert second[0].content == base  # no hint for "gracias"
    stored = await get_session_store().get("s-intent")
    assert stored.case["intent"]["label"] == "complaint"  # "gracias" didn't overwrite it


async def test_handoff_case_has_the_intent(cases):  # noqa: F811
    session = await get_session_store().create("es", {})
    model = ToolCallingFake(replies=[handoff_call(reason="complaint")], calls=[])
    await say(session.id, "Quiero poner una queja, me cobraron una comisión indebida", model, cases)
    [case] = await cases.list_recent()
    assert case["intent"]["label"] == "complaint" and case["intent"]["reason_category"] == "Queja"


def test_turn_log_has_the_intent(agent_client):
    client = agent_client("Claro.")
    sid = client.post("/v1/chat/sessions", json={"lang": "es"}).json()["session_id"]
    client.post(f"/v1/chat/sessions/{sid}/messages", json={"text": "¿cuál es mi saldo?"})
    from app.interactions import get_interaction_store
    from app.main import app

    store = app.dependency_overrides.get(get_interaction_store, get_interaction_store)()
    [turn] = [t for t in store.turns.values() if t["session_id"] == sid]
    assert turn["intent"] == "transactional" and 0 < turn["intent_confidence"] <= 1
