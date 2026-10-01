"""Knowledge search (RAG) for Nova: documents, retrieval, abstention, and the graph around it."""

import json
from pathlib import Path

import yaml
from langchain_core.messages import AIMessage

from app import agent
from app.agent import knowledge
from app.agent.graph import build_graph
from app.agent.knowledge import Chunk, KnowledgeBase, Thresholds, run_search, tokens
from app.sessions import get_session_store
from tests.test_account_tools import ToolCallingFake, call, verified_auth

KNOWLEDGE = Path(knowledge.__file__).parent / "knowledge"


def chunk(id_, lang, title, text, vector=None):
    return Chunk(id_, lang, title, text, "test", vector)


# --- the documents and the index ---------------------------------------------------------------


def test_both_languages_have_the_same_topics_and_every_chunk_has_a_vector():
    chunks, meta = knowledge.load_chunks()
    ids = {lang: {c.id for c in chunks if c.lang == lang} for lang in ("es", "pt")}
    assert ids["es"] == ids["pt"] and len(ids["es"]) >= 18
    assert meta["model"] == "amazon.titan-embed-text-v2:0" and meta["dimensions"] == 512
    assert all(c.vector and len(c.vector) == 512 for c in chunks)


def test_the_index_matches_the_documents():
    """Edit a document without rebuilding the index and the search would answer from old text."""
    chunks, _ = knowledge.load_chunks()
    by_key = {(c.lang, c.id): c for c in chunks}
    for lang in ("es", "pt"):
        for doc in yaml.safe_load((KNOWLEDGE / f"docs_{lang}.yaml").read_text(encoding="utf-8")):
            indexed = by_key[(lang, doc["id"])]
            assert indexed.text == " ".join(doc["text"].split()), f"{lang}/{doc['id']}: rebuild"
            assert indexed.title == doc["title"]


def test_chunks_are_small_and_say_where_they_come_from():
    chunks, _ = knowledge.load_chunks()
    assert max(len(c.text.split()) for c in chunks if not c.id.startswith("branches")) < 130
    assert all(c.source for c in chunks)


def test_every_evaluation_question_points_at_a_real_topic():
    questions = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "ml" / "rag" / "questions.yaml").read_text(
            encoding="utf-8"
        )
    )["questions"]
    chunks, _ = knowledge.load_chunks()
    topics = {c.id for c in chunks}
    assert {q["gold"] for q in questions if q["gold"]} <= topics
    assert {q["split"] for q in questions} == {"dev", "test"}


# --- retrieval ---------------------------------------------------------------------------------


def test_tokens_drop_accents_stopwords_and_cut_to_stems():
    assert tokens("¿Cuánto demora una TRANSFERENCIA?") == ["demora", "transf"]
    assert tokens("transferências") == tokens("transferencias")


async def test_lexical_search_finds_the_right_document_in_each_language(offline_knowledge):
    kb = offline_knowledge
    es = await kb.search("¿Cuánto demora una transferencia a otro banco?", "es")
    assert es.hits[0].chunk.id == "transfers" and es.mode == "lexical"
    pt = await kb.search("Quanto tempo leva para chegar o cartão novo se roubaram o meu?", "pt")
    assert pt.hits[0].chunk.id == "lost-card"
    assert all(h.chunk.lang == "pt" for h in pt.hits)  # never the other language


async def test_run_search_returns_titles_and_sources_or_a_note_to_abstain(offline_knowledge):
    found = json.loads(await run_search({"query": "¿En cuántos días responden un reclamo?"}, "es"))
    assert found["results"][0]["title"].startswith("Cómo funcionan las quejas")
    assert "15 días hábiles" in found["results"][0]["text"]
    nothing = json.loads(await run_search({"query": "¿Cuál es la capital de Francia?"}, "es"))
    assert nothing["results"] == [] and "Do not answer from memory" in nothing["note"]


def test_abstention_needs_both_signals_to_be_weak():
    dense = [
        chunk("a", "es", "A", "gatos negros", [1.0, 0.0]),
        chunk("b", "es", "B", "perros", [0.0, 1.0]),
    ]
    kb = KnowledgeBase(dense, Thresholds(dense=0.5, lexical=0.5, lexical_only=0.3))
    # Off topic for both signals: abstain.
    assert kb.rank("avion", "es", [0.1, 0.1]).abstained is False  # cosine 0.7 is high
    assert kb.rank("avion", "es", [-1.0, -1.0]).abstained is True  # negative cosine, no word shared
    # No lexical match, but the dense signal is strong: answer.
    assert kb.rank("felino", "es", [1.0, 0.0]).abstained is False
    # No dense signal: the lexical threshold alone decides.
    assert kb.rank("avion", "es", None).abstained is True
    assert kb.rank("gatos", "es", None).abstained is False


class FailingEmbedder:
    def __init__(self):
        self.calls = 0

    async def embed_query(self, text):
        self.calls += 1
        raise PermissionError("not allowed to invoke the model")


async def test_a_failing_embedding_falls_back_to_lexical_and_backs_off():
    chunks = [chunk("t", "es", "Transferencias", "transferencia a otro banco", [1.0, 0.0])]
    embedder = FailingEmbedder()
    kb = KnowledgeBase(chunks, Thresholds(), embedder)
    first = await kb.search("transferencia", "es")
    assert first.mode == "lexical" and first.hits[0].chunk.id == "t"
    await kb.search("transferencia", "es")
    assert embedder.calls == 1  # not asked again during the cooldown


class FixedEmbedder:
    async def embed_query(self, text):
        return [1.0, 0.0]


async def test_hybrid_uses_the_dense_signal_when_the_words_do_not_match():
    chunks = [
        chunk("a", "es", "Alfa", "palabras sin relacion", [0.0, 1.0]),
        chunk("b", "es", "Beta", "otro texto distinto", [1.0, 0.0]),
    ]
    result = await KnowledgeBase(chunks, Thresholds(), FixedEmbedder()).search("felino", "es")
    assert result.mode == "hybrid" and result.hits[0].chunk.id == "b"
    assert result.hits[0].dense == 1.0


# --- in the graph ------------------------------------------------------------------------------


async def chat(model, auth, text, lang="es"):
    session = await get_session_store().create(lang, auth)
    agent._graph = build_graph(model)
    try:
        pieces = [p async for p in agent.stream_reply(session.id, text, lang)]
        return "".join(p for p in pieces if isinstance(p, str)), await get_session_store().get(
            session.id
        )
    finally:
        agent._graph = None


def search_call(query):
    return call("search_policies", {"query": query})


async def test_the_model_answers_a_policy_question_from_the_search_without_verification():
    model = ToolCallingFake(
        replies=[search_call("plazo de respuesta de un reclamo"), AIMessage("En 15 días hábiles.")],
        calls=[],
    )
    reply, session = await chat(model, {}, "¿En cuántos días responden un reclamo?")
    assert reply == "En 15 días hábiles."
    # The second model call saw the document, from the tool result.
    result = next(m for m in model.calls[1] if m.type == "tool")
    assert "15 días hábiles" in result.text
    assert session.auth.get("step") is None  # no verification was started
    # The documents consulted are evidence for the human agent and the faithfulness view.
    assert [e["tool"] for e in session.case["evidence"]] == ["search_policies"]


async def test_account_tools_are_still_blocked_without_verification():
    model = ToolCallingFake(replies=[call("get_my_products")], calls=[])
    reply, session = await chat(model, {}, "¿Cuál es mi saldo?")
    assert session.auth["step"] == "awaiting_document"  # verification starts, no data read
    assert "documento" in reply.lower()


async def test_search_and_account_tools_in_one_conversation_when_verified():
    model = ToolCallingFake(
        replies=[
            search_call("tarjeta de crédito cupo"),
            call("get_my_products", i=2),
            AIMessage("ok"),
        ],
        calls=[],
    )
    reply, session = await chat(model, verified_auth(), "¿Qué es el cupo y cuál es el mío?")
    assert reply == "ok"
    assert [e["tool"] for e in session.case["evidence"]] == ["search_policies", "get_my_products"]


async def test_the_offline_model_searches_the_documents(offline_knowledge):
    from app.fake_llm import OfflineChatModel

    agent._graph = build_graph(OfflineChatModel(delay_seconds=0))
    try:
        session = await get_session_store().create("es", {})
        reply = "".join(
            [
                p
                async for p in agent.stream_reply(
                    session.id, "¿Cuál es el plazo de un reclamo?", "es"
                )
            ]
        )
    finally:
        agent._graph = None
    assert "search_policies" in reply and "15 días hábiles" in reply
