"""Faithfulness of Nova's answers to the evidence it consulted (decision 28)."""

import json

from app.agent.faithfulness import analyze, tokens

EVIDENCE = [
    {
        "tool": "get_my_transactions",
        "args": {"status": "declined"},
        "at": "2026-06-17T10:00:00+00:00",
        "result": json.dumps(
            {
                "transactions": [
                    {
                        "transaction_at": "2026-06-13 00:16:00",
                        "amount": 301.05,
                        "currency": "USD",
                        "merchant_name": "TecnoMundo",
                        "transaction_city": "Querétaro",
                    }
                ]
            }
        ),
    },
    {
        "tool": "get_my_products",
        "args": {},
        "at": "2026-06-17T10:00:01+00:00",
        "result": json.dumps(
            {"products": [{"product_type": "Cuenta Corriente", "product_number_last4": "2601",
                           "current_balance": 4850320.75}]}
        ),
    },
]  # fmt: skip


def test_numbers_are_compared_without_separators_or_cents():
    assert tokens("4.850.320,75") == ["4850320"]
    assert tokens("4,850,320.75") == ["4850320"]
    assert tokens("USD 301.05") == ["301", "usd"]
    assert tokens("13 de junio") == ["13", "06"]


def test_supported_and_invented_claims():
    transcript = [
        {"role": "customer", "text": "me rechazaron una compra"},
        {
            "role": "assistant",
            "text": "Hola Lucía. Te rechazaron la compra en **TecnoMundo** del 13 de junio por "
            "USD 301.05. Tu Cuenta Corriente terminada en 2601 tiene $4.850.320. "
            "Tu tarjeta 9999 está bloqueada.",
        },
    ]
    result = analyze(transcript, EVIDENCE, customer_name="Lucía")
    [answer] = result["answers"]
    claims = {c["text"]: c["supported"] for c in answer["claims"]}
    assert claims["TecnoMundo"] and claims["301.05"] and claims["2601"] and claims["4.850.320"]
    assert claims["9999"] is False  # not in any tool result: invented
    assert "Lucía" not in claims  # the greeting isn't a claim
    assert answer["score"] == result["overall"] == round(sum(claims.values()) / len(claims), 3)


def test_sentence_vectors_point_to_the_evidence_they_came_from():
    transcript = [
        {
            "role": "assistant",
            "text": "La compra en TecnoMundo fue de USD 301.05. Tu Cuenta Corriente 2601.",
        }
    ]
    [answer] = analyze(transcript, EVIDENCE)["answers"]
    purchase, account = answer["sentences"]
    assert purchase["similarity"][0] > purchase["similarity"][1]  # transactions, not products
    assert account["similarity"][1] > account["similarity"][0]
    assert "tecnomundo" in purchase["shared"][0]


def test_answers_without_checkable_claims_have_no_score():
    result = analyze([{"role": "assistant", "text": "¡Con gusto! ¿En qué más te ayudo?"}], EVIDENCE)
    assert result["answers"][0]["score"] is None and result["overall"] is None
    assert analyze([], [])["answers"] == []


async def test_console_case_includes_faithfulness(client):
    from app.agent.handoff import InMemoryCaseStore, get_case_store
    from app.main import app

    store = InMemoryCaseStore()
    await store.create(
        {
            "case_id": "NB-1", "session_id": "s", "lang": "es", "status": "waiting",
            "created_at": "2026-06-17T10:00:00+00:00", "reason": "dispute", "summary": "x",
            "open_questions": [], "evidence": EVIDENCE, "messages": [], "agent_name": None,
            "verified_facts": {"first_name": "Lucía"},
            "transcript": [{"role": "assistant", "text": "Compra en TecnoMundo por USD 301.05."}],
        }
    )  # fmt: skip
    app.dependency_overrides[get_case_store] = lambda: store
    try:
        case = client.post("/v1/agent/cases/NB-1", json={"key": "Asesor2026"}).json()
        listed = client.post("/v1/agent/cases", json={"key": "Asesor2026"}).json()
    finally:
        app.dependency_overrides.pop(get_case_store)
    assert case["faithfulness"]["overall"] == 1.0
    assert [e["tool"] for e in case["faithfulness"]["evidence"]] == [
        "get_my_transactions",
        "get_my_products",
    ]
    assert listed["cases"][0]["faithfulness"] == 1.0
    assert listed["stats"]["faithfulness_avg"] == 1.0 and listed["stats"]["waiting"] == 1
