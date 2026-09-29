from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent import graph as graph_module
from app.agent.graph import build_graph
from tests.conftest import parse_sse


class RecordingFake(GenericFakeChatModel):
    """Fake model that records the messages it was called with."""

    calls: list = []

    async def _astream(self, messages, *args, **kwargs):
        self.calls.append(messages)
        async for chunk in super()._astream(messages, *args, **kwargs):
            yield chunk


async def collect(graph, session_id, text, lang):
    from app import agent

    agent._graph = graph
    return "".join([p async for p in agent.stream_reply(session_id, text, lang)])


async def test_stream_reply_streams_model_text():
    model = RecordingFake(messages=iter([AIMessage("Hola, ¿en qué te ayudo?")]), calls=[])
    out = await collect(build_graph(model), "s1", "hola", "es")
    assert out == "Hola, ¿en qué te ayudo?"


async def test_system_prompt_follows_lang_and_memory_is_per_session():
    model = RecordingFake(
        messages=iter([AIMessage("uno"), AIMessage("dois"), AIMessage("otro")]), calls=[]
    )
    graph = build_graph(model)
    await collect(graph, "s1", "primera", "es")
    await collect(graph, "s1", "segunda", "pt")
    await collect(graph, "s2", "nueva", "es")

    first, second, third = model.calls
    assert isinstance(first[0], SystemMessage)
    assert first[0].content == graph_module.system_prompt("es")
    assert second[0].content == graph_module.system_prompt("pt")
    # s1 remembers its first turn; s2 starts clean.
    assert [m.content for m in second[1:]] == ["primera", "uno", "segunda"]
    assert [type(m) for m in third[1:]] == [HumanMessage]


def test_prompts_forbid_secrets_and_invented_data():
    es, pt = graph_module.system_prompt("es"), graph_module.system_prompt("pt")
    assert "PIN" in es and "No inventes saldos" in es
    assert "PIN" in pt and "Não invente saldos" in pt


def test_api_uses_agent_end_to_end(agent_client):
    client = agent_client("Olá! Como posso ajudar?")
    sid = client.post("/v1/chat/sessions", json={"lang": "pt"}).json()["session_id"]
    r = client.post(f"/v1/chat/sessions/{sid}/messages", json={"text": "oi", "lang": "pt"})
    events = parse_sse(r.text)
    assert events[-1][0] == "done"
    assert "".join(d["text"] for e, d in events if e == "token") == "Olá! Como posso ajudar?"
