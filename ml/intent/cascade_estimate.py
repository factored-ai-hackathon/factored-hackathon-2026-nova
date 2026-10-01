# ruff: noqa: E501  (report text)
"""What a cascade would score: the shipped model where it is confident, Claude where it is not.

No new model calls: it combines the shipped classifier's own answers with the predictions that
llm_baseline.py already stored for the same 210 held-out phrases. "Confident" is the threshold the
model was given on training data only (backend/app/agent/intent.py), so nothing here is tuned on the
test set. It is an estimate on a small set, not an implemented feature.

From backend/:  PYTHONPATH=. uv run python ../ml/intent/cascade_estimate.py
Appends a section to ml/intent/LLM_BASELINE.md.
"""

import json
from pathlib import Path

from app.agent import intent

HERE = Path(__file__).parent
CLASSES = ["transactional", "product", "complaint", "technical", "commercial", "retention", "other"]
MARK = "\n## Cascade (estimate)"


def load() -> list[dict]:
    rows = []
    for lang in ("es", "pt"):
        for line in (HERE / f"data/test_{lang}.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line) | {"lang": lang})
    return rows


def macro_f1(truth: list[str], pred: list[str]) -> float:
    total = 0.0
    for c in CLASSES:
        tp = sum(t == c and p == c for t, p in zip(truth, pred, strict=True))
        fp = sum(t != c and p == c for t, p in zip(truth, pred, strict=True))
        fn = sum(t == c and p != c for t, p in zip(truth, pred, strict=True))
        total += 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
    return total / len(CLASSES)


def main() -> None:
    test = load()
    results = json.loads((HERE / "llm_baseline.json").read_text(encoding="utf-8"))
    seen = [intent.classify(r["text"]) for r in test]
    routed = sum(not s.confident for s in seen) / len(test)
    rows = [
        "| Classifier | Macro-F1 | ES | PT | Sent to Claude | Added time (mean) | Cost per 1,000 |",
        "|---|---|---|---|---|---|---|",
    ]

    def line(name, pred, share, ms, cost):
        by = {
            lang: macro_f1([r["label"] for r in test if r["lang"] == lang],
                           [p for r, p in zip(test, pred, strict=True) if r["lang"] == lang])
            for lang in ("es", "pt")
        }  # fmt: skip
        rows.append(
            f"| {name} | {macro_f1([r['label'] for r in test], pred):.3f} | {by['es']:.3f} | {by['pt']:.3f} "
            f"| {share:.0%} | {ms:.0f} ms | ${cost:.2f} |"
        )

    line("shipped model alone", [s.label for s in seen], 0, 0, 0)
    for name in ("claude zero-shot", "claude few-shot"):
        llm = results[name]["predictions"]
        line(
            f"{name} on every message",
            llm,
            1,
            results[name]["latency_ms_p50"],
            results[name]["cost_per_1000"],
        )
        mixed = [llm[i] if not seen[i].confident else seen[i].label for i in range(len(test))]
        line(f"cascade: shipped model, {name} when not confident", mixed, routed,
             routed * results[name]["latency_ms_p50"], routed * results[name]["cost_per_1000"])  # fmt: skip
    section = (
        f"{MARK}\n\nThe shipped model answers when it is confident ({1 - routed:.0%} of the messages); the rest go to "
        "Claude. Computed from the two sets of stored predictions on the same 210 phrases; the confidence threshold "
        "was fixed on training data. An estimate, not implemented, and on a small set the third decimal is noise.\n\n"
        + "\n".join(rows)
        + "\n"
    )
    path = HERE / "LLM_BASELINE.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.split(MARK)[0].rstrip("\n") + "\n" + section, encoding="utf-8")
    print(section)


if __name__ == "__main__":
    main()
