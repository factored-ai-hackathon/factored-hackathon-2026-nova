# ruff: noqa: E501  (report text)
"""Claude as the intent classifier, without training, against the shipped model (decision 29).

The same 210 held-out phrases, the same 7 classes. Two ways of asking Claude Haiku 4.5 on Bedrock:
zero-shot (a definition of each class) and few-shot (the same definitions plus 2 training phrases
per class and language; the test phrases are never shown). Compared with the TF-IDF + logistic
regression the Lambda runs: macro-F1, accuracy, latency per message and cost per 1,000 messages.

From backend/:
    LLM_PROVIDER=bedrock AWS_PROFILE=hackathon PYTHONPATH=. uv run python ../ml/intent/llm_baseline.py

Writes ml/intent/llm_baseline.json and ml/intent/LLM_BASELINE.md. Calls run one after the other, so
the latency is not inflated by our own concurrency.
"""

import json
import statistics
import time
from pathlib import Path

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent import intent
from app.config import get_settings

HERE = Path(__file__).parent
CLASSES = ["transactional", "product", "complaint", "technical", "commercial", "retention", "other"]
DEFINITIONS = """You classify the message a customer writes to a bank's contact center (in Spanish or Portuguese) into exactly one class:
- transactional: balances, movements, transfers, payments, statements, whether a charge or deposit arrived, a declined payment.
- product: information about the bank's products: rates, fees, limits, benefits, requirements, how something works.
- complaint: a complaint or claim about service, treatment, a charge, an unsolved problem; asking to be compensated or to file a formal complaint.
- technical: the app, website, online banking, login, a card reader or ATM that does not work.
- commercial: wanting to buy, request or open a new product or credit.
- retention: wanting to cancel or close a product or leave the bank.
- other: greetings, thanks, goodbyes, small talk or anything unrelated to the bank.
Answer with the class name only, in lowercase, nothing else."""
# Price per million tokens (settings): the cost of the calls is computed from the reported tokens.


def load(split: str) -> list[dict]:
    rows = []
    for lang in ("es", "pt"):
        for line in (HERE / f"data/{split}_{lang}.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line) | {"lang": lang})
    return rows


def few_shot_block(train: list[dict]) -> str:
    lines = ["", "Examples:"]
    for lang in ("es", "pt"):
        for label in CLASSES:
            for row in [r for r in train if r["lang"] == lang and r["label"] == label][:2]:
                lines.append(f'"{row["text"]}" -> {label}')
    return "\n".join(lines)


def f1_scores(truth: list[str], pred: list[str]) -> dict:
    per_class = {}
    for c in CLASSES:
        tp = sum(t == c and p == c for t, p in zip(truth, pred, strict=True))
        fp = sum(t != c and p == c for t, p in zip(truth, pred, strict=True))
        fn = sum(t == c and p != c for t, p in zip(truth, pred, strict=True))
        per_class[c] = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    return {
        "n": len(truth),
        "accuracy": round(sum(t == p for t, p in zip(truth, pred, strict=True)) / len(truth), 3),
        "macro_f1": round(sum(per_class.values()) / len(CLASSES), 3),
        "f1_by_class": {c: round(v, 3) for c, v in per_class.items()},
    }


def ask(llm, system: str, text: str) -> tuple[str, int, int, int]:
    started = time.perf_counter()
    reply = llm.invoke([SystemMessage(system), HumanMessage(text)])
    ms = round((time.perf_counter() - started) * 1000)
    label = reply.text.strip().lower().strip(".\"' ")
    usage = reply.usage_metadata or {}
    return (
        (label if label in CLASSES else "other"),
        ms,
        usage.get("input_tokens", 0),
        usage.get("output_tokens", 0),
    )


def main() -> None:
    settings = get_settings()
    test, train = load("test"), load("train")
    llm = ChatBedrockConverse(
        model=settings.bedrock_model_id,
        region_name=settings.aws_region,
        temperature=0,
        max_tokens=8,
    )
    price_in, price_out = settings.llm_price_input_per_mtok, settings.llm_price_output_per_mtok
    truth = [r["label"] for r in test]

    results = {}
    started = time.perf_counter()
    shipped = [intent.classify(r["text"]).label for r in test]
    shipped_ms = (time.perf_counter() - started) * 1000 / len(test)
    results["tfidf+logreg (shipped)"] = {
        **f1_scores(truth, shipped),
        "by_language": {
            lang: f1_scores([r["label"] for r in test if r["lang"] == lang],
                            [p for r, p in zip(test, shipped, strict=True) if r["lang"] == lang])
            for lang in ("es", "pt")
        },
        "latency_ms_p50": round(shipped_ms, 2), "cost_per_1000": 0.0,
    }  # fmt: skip

    for name, system in (
        ("claude zero-shot", DEFINITIONS),
        ("claude few-shot", DEFINITIONS + "\n" + few_shot_block(train)),
    ):
        preds, ms, cost = [], [], 0.0
        for i, row in enumerate(test):
            label, took, tin, tout = ask(llm, system, row["text"])
            preds.append(label)
            ms.append(took)
            cost += (tin * price_in + tout * price_out) / 1_000_000
            if i % 50 == 0:
                print(name, i, flush=True)
        results[name] = {
            **f1_scores(truth, preds),
            "by_language": {
                lang: f1_scores([r["label"] for r in test if r["lang"] == lang],
                                [p for r, p in zip(test, preds, strict=True) if r["lang"] == lang])
                for lang in ("es", "pt")
            },
            "latency_ms_p50": statistics.median(ms),
            "latency_ms_p95": sorted(ms)[int(0.95 * (len(ms) - 1))],
            "cost_per_1000": round(1000 * cost / len(test), 4),
            "predictions": preds,
        }  # fmt: skip
    (HERE / "llm_baseline.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    rows = [
        "| Classifier | Macro-F1 | ES | PT | Accuracy | Latency p50 | Cost per 1,000 messages |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, r in results.items():
        latency = (
            f"{r['latency_ms_p50'] / 1000:.2f} s"
            if r["latency_ms_p50"] > 5
            else f"{r['latency_ms_p50']:.1f} ms"
        )
        rows.append(
            f"| {name} | {r['macro_f1']:.3f} | {r['by_language']['es']['macro_f1']:.3f} "
            f"| {r['by_language']['pt']['macro_f1']:.3f} | {r['accuracy']:.3f} | {latency} | ${r['cost_per_1000']:.2f} |"
        )
    md = (
        "# Claude as the intent classifier (generated by llm_baseline.py)\n\n"
        f"{len(test)} held-out, team-written phrases (105 ES, 105 PT), the same ones as the model card. "
        "Claude Haiku 4.5 on Bedrock, temperature 0; few-shot shows 2 training phrases per class and language.\n\n"
        + "\n".join(rows)
        + "\n"
    )
    (HERE / "LLM_BASELINE.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
