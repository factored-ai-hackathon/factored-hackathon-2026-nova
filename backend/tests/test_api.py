from tests.conftest import parse_sse


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "llm_provider": "huggingface"}


def test_create_session_default_lang(client):
    r = client.post("/v1/chat/sessions")
    assert r.status_code == 201
    body = r.json()
    assert body["lang"] == "es"
    assert len(body["session_id"]) == 36


def test_create_session_pt(client):
    r = client.post("/v1/chat/sessions", json={"lang": "pt"})
    assert r.status_code == 201
    assert r.json()["lang"] == "pt"


def test_create_session_bad_lang(client):
    assert client.post("/v1/chat/sessions", json={"lang": "en"}).status_code == 422


def test_message_streams_tokens_then_done(client):
    sid = client.post("/v1/chat/sessions").json()["session_id"]
    r = client.post(f"/v1/chat/sessions/{sid}/messages", json={"text": "hola banco", "lang": "es"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    names = [e for e, _ in events]
    assert names == ["token", "token", "done"]
    assert "".join(d["text"] for e, d in events if e == "token") == "hola banco "
    assert len(events[-1][1]["message_id"]) == 36


def test_message_unknown_session(client):
    r = client.post("/v1/chat/sessions/nope/messages", json={"text": "hola", "lang": "es"})
    assert r.status_code == 404


def test_message_empty_text(client):
    sid = client.post("/v1/chat/sessions").json()["session_id"]
    for text in ["", "   "]:
        r = client.post(f"/v1/chat/sessions/{sid}/messages", json={"text": text, "lang": "es"})
        assert r.status_code == 422


def test_message_too_long(client):
    sid = client.post("/v1/chat/sessions").json()["session_id"]
    url = f"/v1/chat/sessions/{sid}/messages"
    assert client.post(url, json={"text": "a" * 2000, "lang": "es"}).status_code == 200
    assert client.post(url, json={"text": "a" * 2001, "lang": "es"}).status_code == 422


def test_stream_error_event(client):
    from app.api.chat import get_reply_streamer
    from app.main import app

    async def failing(session_id, text, lang, usage=None):
        yield "partial "
        raise RuntimeError("boom")

    app.dependency_overrides[get_reply_streamer] = lambda: failing
    sid = client.post("/v1/chat/sessions").json()["session_id"]
    r = client.post(f"/v1/chat/sessions/{sid}/messages", json={"text": "hola", "lang": "es"})
    events = parse_sse(r.text)
    assert [e for e, _ in events] == ["token", "error"]
    assert events[-1][1]["code"] == "llm_error"
    assert "boom" not in events[-1][1]["message"]
