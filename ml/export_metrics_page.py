"""Exports the measured model results for the frontend's /modelos page.

Offline: reads only files already in the repo (no Bedrock, no AWS). The question vectors come from
the cache that evaluate.py wrote (ml/rag/query_vectors.json).

From backend/ (needs the backend's knowledge search code):
    PYTHONPATH=. uv run python ../ml/export_metrics_page.py

Writes frontend/src/data/modelMetrics.json. Run it again after train.py, llm_baseline.py,
ablation.py, build_index.py, evaluate.py or a new evals/report run;
backend/tests/test_metrics_page.py fails while the committed file is stale.
"""

import json
import math
import sys
from pathlib import Path

import yaml

ML = Path(__file__).resolve().parent
ROOT = ML.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ML / "rag"))

from evaluate import RETRIEVERS, VECTORS, Scorer  # noqa: E402

from app.agent.knowledge import KnowledgeBase, _cosine, load_chunks, load_thresholds  # noqa: E402

OUT = ROOT / "frontend" / "src" / "data" / "modelMetrics.json"
# The reported evaluation run (evals/report/REPORT.md): real Bedrock token counts per conversation.
COST_RUN = ROOT / "evals" / "report" / "results" / "run6.json"
# Titan Text Embeddings V2 on Bedrock, per million tokens (ml/rag/README.md).
TITAN_PRICE_PER_MTOK = 0.02


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _r(x: float | None, digits: int = 3) -> float | None:
    return None if x is None else round(x, digits)


# --- intent classifier ------------------------------------------------------------------------


def _ablation_summary(ablation: dict) -> dict:
    """Runs that opened a case or offered a person, by group and hint (README's ablation table)."""
    out: dict = {}
    for run in ablation["runs"]:
        key = f"{run['group']}_{'on' if run['hint_on'] else 'off'}"
        cell = out.setdefault(key, {"runs": 0, "person": 0, "opened": 0})
        cell["runs"] += 1
        cell["person"] += bool(run["opened"] or run["offered"])
        cell["opened"] += bool(run["opened"])
    summary = ablation["summary"]
    return {
        "repeats": summary["repeats"],
        "group_sizes": summary["group_sizes"],
        "classifier_fired": summary["classifier_fired"],
        "paired": summary["paired"],
        "cells": out,
    }


def intent() -> dict:
    m = _read(ML / "intent" / "metrics.json")
    llm = _read(ML / "intent" / "llm_baseline.json")
    rates = _read(ML / "intent" / "resolution_rates.json")["by_intent"]

    def scores(block: dict) -> dict:
        return {k: block[k] for k in ("accuracy", "macro_f1", "f1_by_class")}

    def llm_row(name: str, key: str) -> dict:
        b = llm[key]
        return {
            "name": name,
            "macro_f1": b["macro_f1"],
            "es": b["by_language"]["es"]["macro_f1"],
            "pt": b["by_language"]["pt"]["macro_f1"],
            "f1_by_class": b["f1_by_class"],
            "latency_ms": b["latency_ms_p50"],
            "cost_per_1000": b["cost_per_1000"],
        }

    return {
        "classes": m["data"]["classes"],
        "data": {k: m["data"][k] for k in ("train", "test")},
        "leakage": m["leakage"]["nearest_train_jaccard_char4"],
        "selection": {
            "best": m["selection"]["best"],
            "grid": m["selection"]["grid"],
            "threshold": m["selection"]["threshold"],
        },
        "test": {
            "majority": scores(m["majority_baseline"]["test"]),
            "keywords": scores(m["keyword_baseline"]["test"]),
            "model": scores(m["model"]["test"]),
        },
        "by_language": {
            lang: {name: scores(block) for name, block in by.items()}
            for lang, by in m["by_language"].items()
        },
        "calibration": {
            k: m["model"]["test"][k] for k in ("ece", "confident_coverage", "confident_accuracy")
        },
        "confusion": m["confusion_matrix"],
        "llm": [
            llm_row("TF-IDF + regresión logística", "tfidf+logreg (shipped)"),
            llm_row("Claude zero-shot", "claude zero-shot"),
            llm_row("Claude few-shot", "claude few-shot"),
        ],
        "fcr": {
            k: {"fcr": v["fcr_rate"], "interactions": v["interactions"]} for k, v in rates.items()
        },
        "ablation": _ablation_summary(_read(ML / "intent" / "ablation.json")),
    }


# --- knowledge search (RAG) ---------------------------------------------------------------------


def _pca2(points: list[list[float]]) -> tuple[list[float], list[list[float]], list[float]]:
    """Mean, the first two principal axes and their share of the variance (power iteration on the
    Gram matrix: 42 points, so it is small and needs no numpy)."""
    n, d = len(points), len(points[0])
    mean = [sum(p[j] for p in points) / n for j in range(d)]
    x = [[p[j] - mean[j] for j in range(d)] for p in points]
    gram = [
        [sum(a * b for a, b in zip(x[i], x[k], strict=True)) for k in range(n)] for i in range(n)
    ]
    total = sum(gram[i][i] for i in range(n))
    axes, shares = [], []
    for _ in range(2):
        u = [1.0 + i / n for i in range(n)]
        value = 0.0
        for _ in range(500):
            w = [sum(gram[i][k] * u[k] for k in range(n)) for i in range(n)]
            norm = math.sqrt(sum(v * v for v in w))
            u = [v / norm for v in w]
            value = norm
        axis = [sum(x[i][j] * u[i] for i in range(n)) for j in range(d)]
        length = math.sqrt(sum(v * v for v in axis))
        axis = [v / length for v in axis]
        if max(axis, key=abs) < 0:  # a fixed sign, so the picture doesn't flip between runs
            axis = [-v for v in axis]
        axes.append(axis)
        shares.append(value / total)
        gram = [[gram[i][k] - value * u[i] * u[k] for k in range(n)] for i in range(n)]
    return mean, axes, shares


def _project(v: list[float], mean: list[float], axes: list[list[float]]) -> list[float]:
    centered = [a - b for a, b in zip(v, mean, strict=True)]
    return [round(sum(a * b for a, b in zip(centered, axis, strict=True)), 4) for axis in axes]


def rag() -> dict:
    metrics = _read(ML / "rag" / "metrics.json")
    chunks, meta = load_chunks()
    questions = yaml.safe_load((ML / "rag" / "questions.yaml").read_text(encoding="utf-8"))[
        "questions"
    ]
    vectors = {qid: item["v"] for qid, item in _read(VECTORS).items()}
    kb = KnowledgeBase(chunks)
    scorer = Scorer(kb)
    thresholds = load_thresholds()

    mean, axes, shares = _pca2([c.vector for c in chunks])
    chunk_rows = [
        {
            "id": c.id,
            "lang": c.lang,
            "title": c.title,
            "words": len(c.text.split()),
            "xy": _project(c.vector, mean, axes),
        }
        for c in chunks
    ]

    # Same topic in the other language against every other topic: is the embedding multilingual?
    by_id: dict[str, dict[str, list[float]]] = {}
    for c in chunks:
        by_id.setdefault(c.id, {})[c.lang] = c.vector
    pairs = [(t, v["es"], v["pt"]) for t, v in by_id.items() if "es" in v and "pt" in v]
    same = [_cosine(es, pt) for _, es, pt in pairs]
    other = [_cosine(a[1], b[2]) for a in pairs for b in pairs if a[0] != b[0]]

    rows = []
    for q in questions:
        if q["split"] != "test":
            continue
        lang_chunks = kb.by_lang[q["lang"]]
        ids = [c.id for c in lang_chunks]
        scores = scorer.scores(q, vectors[q["id"]])
        ranks = {}
        for name in RETRIEVERS:
            order = sorted(range(len(ids)), key=lambda i, s=scores[name]: s[i], reverse=True)
            ranked = [ids[i] for i in order]
            ranks[name] = ranked.index(q["gold"]) + 1 if q["gold"] else None
        dense = scores["dense"]
        gold_cos = dense[ids.index(q["gold"])] if q["gold"] else None
        other_cos = max(s for i, s in zip(ids, dense, strict=True) if i != q["gold"])
        kb.thresholds = thresholds
        result = kb.rank(q["q"], q["lang"], vectors[q["id"]])
        rows.append(
            {
                "id": q["id"],
                "lang": q["lang"],
                "q": q["q"],
                "gold": q["gold"],
                "ranks": ranks,
                "gold_cos": _r(gold_cos),
                "best_other_cos": _r(other_cos),
                "top_cos": _r(result.top_dense),
                "top_lexical": _r(result.top_lexical),
                "abstained": result.abstained,
                "top_hit": result.hits[0].chunk.id if result.hits else None,
                "xy": _project(vectors[q["id"]], mean, axes),
            }
        )

    return {
        "embedding": {
            "model": meta["model"],
            "dimensions": meta["dimensions"],
            "pca_variance": [round(s, 3) for s in shares],
        },
        "crosslingual": {
            "same_topic": [
                {"id": t, "cos": round(s, 3)} for (t, _, _), s in zip(pairs, same, strict=True)
            ],
            "other_topic_mean": round(sum(other) / len(other), 3),
            "other_topic_max": round(max(other), 3),
        },
        "chunks": chunk_rows,
        "questions": {"dev": metrics["questions"]["dev"], "test": metrics["questions"]["test"]},
        "thresholds": metrics["thresholds"],
        "ranking": metrics["ranking"],
        "abstention": metrics["abstention"],
        "test_questions": rows,
    }


# --- cost per token ------------------------------------------------------------------------------


def cost() -> dict:
    """What a conversation costs, from the tokens Bedrock reported in the evaluation run."""
    run = _read(COST_RUN)
    price = run["meta"]["price_per_mtok"]
    runs = [r for r in run["runs"] if not r["error"]]

    def summary(group: list[dict]) -> dict:
        n = len(group)
        tokens_in = sum(r["input_tokens"] for r in group)
        tokens_out = sum(r["output_tokens"] for r in group)
        messages = sum(len(r["said"]) for r in group)
        cost_in = tokens_in * price["input"] / 1e6
        cost_out = tokens_out * price["output"] / 1e6
        return {
            "conversations": n,
            "messages": messages,
            "input_tokens_per_conversation": round(tokens_in / n),
            "output_tokens_per_conversation": round(tokens_out / n),
            "cost_per_conversation": round((cost_in + cost_out) / n, 6),
            "cost_per_message": round((cost_in + cost_out) / messages, 6),
            "input_share_of_cost": round(cost_in / (cost_in + cost_out), 3),
        }

    kinds: dict[str, list[dict]] = {}
    for r in runs:
        kinds.setdefault(r["kind"], []).append(r)
    costs = sorted(r["cost_usd"] for r in runs)
    return {
        "source": f"evals/report/results/{COST_RUN.name}",
        "model": run["meta"]["model"],
        "price_per_mtok": price,
        "price_per_token": {k: v / 1e6 for k, v in price.items()},
        "all": summary(runs),
        "p95_per_conversation": round(costs[int(0.95 * (len(costs) - 1))], 6),
        "by_kind": {k: summary(v) for k, v in sorted(kinds.items())},
        "titan_price_per_mtok": TITAN_PRICE_PER_MTOK,
    }


def build() -> dict:
    return {
        "generated_by": "ml/export_metrics_page.py",
        "intent": intent(),
        "rag": rag(),
        "cost": cost(),
    }


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


if __name__ == "__main__":
    OUT.write_text(dumps(build()), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")
