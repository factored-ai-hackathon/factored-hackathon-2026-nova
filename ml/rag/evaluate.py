"""Evaluates the knowledge search on held-out questions, against its baselines, and calibrates the
abstention thresholds on the dev split only (decision 32).

From backend/ (Bedrock the first time, to embed the questions; they are cached afterwards in
ml/rag/query_vectors.json, so the evaluation is repeatable offline):
    AWS_PROFILE=hackathon PYTHONPATH=. uv run python ../ml/rag/evaluate.py

Writes ml/rag/metrics.json, ml/rag/RESULTS.md and backend/app/agent/knowledge/thresholds.json.

Retrievers compared (same chunks, same language filter):
  bm25-words    BM25 over accent-free words (the plain lexical baseline)
  bm25-stems    BM25 over words cut to 6 letters (the lexical part of the shipped search)
  dense         Titan Text Embeddings V2 cosine similarity
  hybrid        bm25-stems + dense, reciprocal rank fusion (the shipped search)
Ranking metrics use the answerable test questions. Abstention uses all test questions: for the
unanswerable ones the right behavior is to return nothing.
"""

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))

from app.agent.knowledge import (  # noqa: E402
    THRESHOLDS_PATH,
    KnowledgeBase,
    Thresholds,
    TitanEmbedder,
    _Bm25,
    _cosine,
    load_chunks,
)
from app.config import get_settings  # noqa: E402

VECTORS = HERE / "query_vectors.json"
RETRIEVERS = ("bm25-words", "bm25-stems", "dense", "hybrid")


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def rate(k: int, n: int) -> dict:
    return {"k": k, "n": n, "rate": round(k / n, 3) if n else None, "ci95": wilson(k, n)}


def question_vectors(questions: list[dict], refresh: bool) -> dict[str, list[float]]:
    cached = json.loads(VECTORS.read_text()) if VECTORS.exists() and not refresh else {}
    missing = [q for q in questions if q["id"] not in cached or cached[q["id"]]["q"] != q["q"]]
    if missing:
        settings = get_settings()
        embedder = TitanEmbedder("amazon.titan-embed-text-v2:0", settings.aws_region, 512)
        for q in missing:
            cached[q["id"]] = {"q": q["q"], "v": [round(x, 5) for x in embedder._embed(q["q"])]}
        VECTORS.write_text(json.dumps(cached, ensure_ascii=False, separators=(",", ":")))
        print(f"embedded {len(missing)} questions")
    return {qid: item["v"] for qid, item in cached.items()}


class Scorer:
    """The four retrievers' scores for a question, over the chunks of its language."""

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        self.words = {
            lang: _Bm25([c.searchable for c in group], stems=False)
            for lang, group in kb.by_lang.items()
        }

    def scores(self, q: dict, vector: list[float]) -> dict[str, list[float]]:
        chunks = self.kb.by_lang[q["lang"]]
        words, _ = self.words[q["lang"]].scores(q["q"])
        stems, _ = self.kb._bm25[q["lang"]].scores(q["q"])
        dense = [_cosine(vector, c.vector) for c in chunks]
        # The shipped search itself (its fusion rules included), without abstaining.
        saved, self.kb.thresholds = self.kb.thresholds, Thresholds()
        try:
            hits = self.kb.rank(q["q"], q["lang"], vector, k=len(chunks)).hits
        finally:
            self.kb.thresholds = saved
        fused = {h.chunk.id: h.score for h in hits}
        hybrid = [fused[c.id] for c in chunks]
        return {"bm25-words": words, "bm25-stems": stems, "dense": dense, "hybrid": hybrid}


def ranking_metrics(rows: list[dict]) -> dict:
    out = {}
    for name in RETRIEVERS:
        hits1 = hits3 = 0
        rr = []
        for r in rows:
            ids = [c.id for c in r["chunks"]]
            order = sorted(range(len(ids)), key=lambda i: r["scores"][name][i], reverse=True)
            ranked = [ids[i] for i in order]
            position = ranked.index(r["gold"]) if r["gold"] in ranked else None
            hits1 += position == 0
            hits3 += position is not None and position < 3
            rr.append(1 / (position + 1) if position is not None else 0.0)
        out[name] = {
            "n": len(rows),
            "recall@1": rate(hits1, len(rows)),
            "recall@3": rate(hits3, len(rows)),
            "mrr": round(sum(rr) / len(rr), 3) if rr else None,
        }
    return out


def decisions(kb: KnowledgeBase, rows: list[dict], thresholds: Thresholds, dense: bool) -> dict:
    """Answer-or-abstain quality for every row (answerable and not) at these thresholds."""
    kb.thresholds = thresholds
    wrong_answers = wrong_abstains = correct = 0
    top1 = 0
    answerable = [r for r in rows if r["gold"]]
    for r in rows:
        result = kb.rank(r["q"]["q"], r["q"]["lang"], r["vector"] if dense else None)
        if r["gold"] is None:
            wrong_answers += not result.abstained
            correct += result.abstained
        else:
            wrong_abstains += result.abstained
            correct += not result.abstained
            top1 += bool(result.hits) and result.hits[0].chunk.id == r["gold"]
    unanswerable = len(rows) - len(answerable)
    return {
        "decision_accuracy": rate(correct, len(rows)),
        "answered_unanswerable": rate(wrong_answers, unanswerable),
        "abstained_answerable": rate(wrong_abstains, len(answerable)),
        "answered_with_gold_on_top": rate(top1, len(answerable)),
    }


MAX_ABSTAIN_ON_ANSWERABLE = 0.0


def calibrate(kb: KnowledgeBase, dev: list[dict]) -> Thresholds:
    """Thresholds from the dev split only. The search's job is recall: it may only drop a question
    when it is clearly off topic, so the thresholds are the ones that abstain on the most
    unanswerable dev questions while abstaining on none of the answerable ones (chosen on 50
    questions, a threshold is not trusted to give up more: with a 5% allowance it dropped 24% of
    the test questions). The
    near-misses (a branch "in Chile") are left to the model, which reads the chunks and says
    when they don't answer (evals/agent/knowledge.yaml). Ties go to the lowest thresholds."""
    answerable = sum(r["gold"] is not None for r in dev)
    allowed = int(MAX_ABSTAIN_ON_ANSWERABLE * answerable)

    def score(t: Thresholds, dense: bool) -> tuple[int, int] | None:
        d = decisions(kb, dev, t, dense)
        if d["abstained_answerable"]["k"] > allowed:
            return None
        caught = d["answered_unanswerable"]["n"] - d["answered_unanswerable"]["k"]
        return caught, d["answered_with_gold_on_top"]["k"]

    lex_grid = [round(i / 40, 3) for i in range(0, 41)]
    dense_grid = [round(0.10 + i * 0.01, 2) for i in range(0, 51)]

    def best(candidates):
        ranked = [(score(t, dense), t) for t, dense in candidates]
        ranked = [(s, t) for s, t in ranked if s is not None]
        top = max(s for s, _ in ranked)
        return min(
            (t for s, t in ranked if s == top), key=lambda t: (t.dense, t.lexical, t.lexical_only)
        )

    only = best((Thresholds(lexical_only=x), False) for x in lex_grid)
    hybrid = best(
        (Thresholds(dense=d, lexical=x), True) for d, x in itertools.product(dense_grid, lex_grid)
    )
    return Thresholds(dense=hybrid.dense, lexical=hybrid.lexical, lexical_only=only.lexical_only)


def table(title: str, header: list[str], rows: list[list[str]]) -> str:
    lines = [f"### {title}", "", "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def pct(r: dict) -> str:
    return f"{100 * r['rate']:.0f}% ({r['k']}/{r['n']})" if r["rate"] is not None else "n/a"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="embed the questions again")
    args = parser.parse_args()

    questions = yaml.safe_load((HERE / "questions.yaml").read_text(encoding="utf-8"))["questions"]
    chunks, meta = load_chunks()
    assert meta.get("model"), "build the index with vectors first (build_index.py)"
    kb = KnowledgeBase(chunks)
    scorer = Scorer(kb)
    vectors = question_vectors(questions, args.refresh)
    rows = []
    for q in questions:
        chunk_ids = {c.id for c in kb.by_lang[q["lang"]]}
        assert q["gold"] is None or q["gold"] in chunk_ids, f"{q['id']}: unknown topic {q['gold']}"
        rows.append(
            {
                "q": q,
                "gold": q["gold"],
                "vector": vectors[q["id"]],
                "chunks": kb.by_lang[q["lang"]],
                "scores": scorer.scores(q, vectors[q["id"]]),
            }
        )
    dev = [r for r in rows if r["q"]["split"] == "dev"]
    test = [r for r in rows if r["q"]["split"] == "test"]

    thresholds = calibrate(kb, dev)
    THRESHOLDS_PATH.write_text(
        json.dumps(
            {
                "thresholds": thresholds.__dict__,
                "calibrated_on": f"dev split of ml/rag/questions.yaml ({len(dev)} questions)",
            },
            indent=1,
        )
    )

    answerable_test = [r for r in test if r["gold"]]
    result = {
        "chunks": len(chunks),
        "questions": {"dev": len(dev), "test": len(test)},
        "thresholds": thresholds.__dict__,
        "ranking": {
            "all": ranking_metrics(answerable_test),
            **{
                lang: ranking_metrics([r for r in answerable_test if r["q"]["lang"] == lang])
                for lang in ("es", "pt")
            },
        },
        "abstention": {
            "hybrid": {
                "test": decisions(kb, test, thresholds, True),
                "dev (calibration)": decisions(kb, dev, thresholds, True),
            },
            "lexical-only (fallback)": {
                "test": decisions(kb, test, thresholds, False),
                "dev (calibration)": decisions(kb, dev, thresholds, False),
            },
        },
    }
    (HERE / "metrics.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))

    md = [
        "# Knowledge search results (generated by evaluate.py)\n",
        f"{len(chunks)} chunks (ES + PT), {len(dev)} dev and {len(test)} test questions "
        "(team-written, held-out; the dev split only chooses the abstention thresholds).\n",
    ]
    for scope in ("all", "es", "pt"):
        rk = result["ranking"][scope]
        md.append(
            table(
                f"Ranking, answerable test questions ({scope}, n={rk['dense']['n']})",
                ["Retriever", "Recall@1", "Recall@3", "MRR"],
                [
                    [n, pct(rk[n]["recall@1"]), pct(rk[n]["recall@3"]), f"{rk[n]['mrr']:.3f}"]
                    for n in RETRIEVERS
                ],
            )
        )
    t = thresholds
    md.append(
        f"Abstention thresholds (dev only): hybrid dense cosine < {t.dense} and lexical "
        f"coverage < {t.lexical}; lexical-only fallback coverage < {t.lexical_only}.\n"
    )
    for mode, by_split in result["abstention"].items():
        md.append(
            table(
                f"Answer or abstain: {mode}",
                [
                    "Split",
                    "Decision accuracy",
                    "Answered an unanswerable",
                    "Abstained on an answerable",
                    "Gold chunk on top",
                ],
                [
                    [
                        split,
                        pct(d["decision_accuracy"]),
                        pct(d["answered_unanswerable"]),
                        pct(d["abstained_answerable"]),
                        pct(d["answered_with_gold_on_top"]),
                    ]
                    for split, d in by_split.items()
                ],
            )
        )
    (HERE / "RESULTS.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
