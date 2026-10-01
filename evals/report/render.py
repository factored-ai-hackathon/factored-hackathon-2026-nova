# ruff: noqa: E501  (the report text is long Markdown lines)
"""Writes REPORT.md from a results JSON of run_report.py.

    uv run python ../evals/report/render.py ../evals/report/results/run1.json ../evals/report/results/run2.json

With two files the first is the run before the fixes the first one led to, the last is the final
run. Every run is re-scored from its stored replies with the current cases.yaml and metrics.py (the
corrections listed in cases.yaml), so a scorer fix never needs a new model run.

The text around the numbers (what was measured, limitations) is fixed here; the numbers come
from the run, never typed by hand.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import yaml  # noqa: E402
from metrics import UNSAFE_TYPES, by, judge, summarize  # noqa: E402

LANGS = {"es": "Spanish", "pt": "Portuguese"}


def pct(r: dict | None, ci: bool = True) -> str:
    if not r or r["rate"] is None:
        return "n/a"
    text = f"{100 * r['rate']:.1f}% ({r['k']}/{r['n']})"
    if ci and r["ci95"]:
        text += f" [{100 * r['ci95'][0]:.0f}-{100 * r['ci95'][1]:.0f}]"
    return text


def secs(ms: float | None) -> str:
    return "n/a" if ms is None else f"{ms / 1000:.1f} s"


def usd(value: float | None, digits: int = 4) -> str:
    return "n/a" if value is None else f"${value:.{digits}f}"


def num(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def headline(summaries: dict[str, dict]) -> str:
    cols = list(summaries)
    rows = [
        ("Safe automated resolution", lambda s: pct(s["safe_automated_resolution"])),
        ("Containment (no person took over)", lambda s: pct(s["containment"])),
        (
            "Safe containment (no person needed, nothing wrong)",
            lambda s: pct(s["safe_containment"]),
        ),
        ("Escalation recall (handed over when it should)", lambda s: pct(s["escalation_recall"])),
        (
            "Escalation recall, counting a clear offer of a person",
            lambda s: pct(s["escalation_recall_or_offer"]),
        ),
        (
            "Escalation precision (handovers that were needed: cases that must be handed over, or ask for an action the bot cannot do)",
            lambda s: pct(s["escalation_precision"]),
        ),
        ("Escalation with the right reason", lambda s: pct(s["escalation_reason_correct"])),
        (
            "Case for the human complete (facts, summary, evidence)",
            lambda s: pct(s["case_completeness"]),
        ),
        ("Runs with an unsafe outcome", lambda s: pct(s["unsafe_runs"])),
        ("Runs that did what the case expects", lambda s: pct(s["pass_rate"])),
        ("Latency per customer message, p50", lambda s: secs(s["latency_ms"]["p50"])),
        ("Latency per customer message, p95", lambda s: secs(s["latency_ms"]["p95"])),
        (
            "Time to first token, p50 / p95",
            lambda s: (
                f"{secs(s['latency_ms']['first_token_p50'])} / {secs(s['latency_ms']['first_token_p95'])}"
            ),
        ),
        ("Cost per case, mean", lambda s: usd(s["cost_usd"]["mean_per_case"])),
        ("Cost per case, p95", lambda s: usd(s["cost_usd"]["p95_per_case"])),
        ("Cost per 1,000 cases", lambda s: usd(s["cost_usd"]["per_1000_cases"], 2)),
        ("Faithfulness of answers that used data (mean)", lambda s: num(s["faithfulness_mean"])),
        ("Reply in the wrong language (runs)", lambda s: str(s["language_errors"])),
    ]
    out = ["| Metric | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for name, fn in rows:
        out.append(f"| {name} | " + " | ".join(fn(summaries[c]) for c in cols) + " |")
    return "\n".join(out)


def by_kind(runs: list[dict]) -> str:
    out = ["| Kind | Expected behavior | Cases | Runs | Passed |", "|---|---|---|---|---|"]
    expectation = {
        "account": "resolve with the customer's data",
        "public": "resolve (hours, branches, open an account) or stay in scope",
        "verification": "verify in the chat, then resolve",
        "ambiguous": "ask one question",
        "handoff": "hand over to a person",
        "unsupported": "do not claim the action; explain or hand over",
        "unsafe": "leak nothing, follow nothing",
    }
    for kind, group in by(runs, lambda r: r["kind"]).items():
        passed = sum(r["passed"] for r in group)
        out.append(
            f"| {kind} | {expectation[kind]} | {len({r['id'] for r in group})} | {len(group)} "
            f"| {100 * passed / len(group):.0f}% ({passed}/{len(group)}) |"
        )
    return "\n".join(out)


def unsafe_table(summaries: dict[str, dict]) -> str:
    cols = list(summaries)
    out = ["| Unsafe outcome | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    meaning = {
        "secret_request": "asked for a PIN, password or card number",
        "cross_customer_read": "read another customer's data",
        "read_before_verification": "read data without a verified session",
        "forbidden_content": "showed another customer's data, secrets or its instructions",
        "claimed_action": "said an unsupported action (transfer, block, change) was done",
        "invented_amount": "stated money amounts without having read any data",
    }
    for t in UNSAFE_TYPES:
        out.append(
            f"| {meaning[t]} | "
            + " | ".join(str(summaries[c]["unsafe_by_type"][t]) for c in cols)
            + " |"
        )
    return "\n".join(out)


def failures(runs: list[dict], cases: dict[str, dict]) -> str:
    bad: dict[str, list[dict]] = {}
    for r in runs:
        if not r["passed"]:
            bad.setdefault(r["id"], []).append(r)
    if not bad:
        return "No run failed."
    out = [
        "| Case | Failed runs | Why | What the agent said (first failing run) |",
        "|---|---|---|---|",
    ]
    for case_id, group in sorted(bad.items()):
        first = group[0]
        why = "; ".join(sorted({p for r in group for p in r["problems"] + r["unsafe"]})) or (
            first["error"] or ""
        )
        reply = (
            (first["replies"][-1] if first["replies"] else first["error"] or "")
            .replace("\n", " ")
            .replace("|", "/")
        )
        total = sum(1 for r in runs if r["id"] == case_id)
        out.append(f"| `{case_id}` | {len(group)}/{total} | {why} | {reply[:220]} |")
    return "\n".join(out)


def ml_section() -> str:
    path = HERE.parent.parent / "ml" / "intent" / "metrics.json"
    if not path.exists():
        return ""
    m = json.loads(path.read_text(encoding="utf-8"))
    test = m["model"]["test"]
    kw, mj = m["keyword_baseline"]["test"], m["majority_baseline"]["test"]
    es, pt = m["by_language"]["es"], m["by_language"]["pt"]
    return f"""## The learned component against its baselines (decision 29)

The intent classifier (TF-IDF + logistic regression, run in plain Python in the Lambda) reads
each customer message in code; for complaints and retention it tells Nova to offer a person
sooner. Held-out test: {test["n"]} team-written phrases, written separately from the training
phrases, with a leakage check (`ml/README.md`).

| | Accuracy | Macro-F1 | ES macro-F1 | PT macro-F1 |
|---|---|---|---|---|
| Majority class | {mj["accuracy"]:.3f} | {mj["macro_f1"]:.3f} | | |
| Keyword rules (ES + PT) | {kw["accuracy"]:.3f} | {kw["macro_f1"]:.3f} | {es["keyword_baseline"]["macro_f1"]:.3f} | {pt["keyword_baseline"]["macro_f1"]:.3f} |
| **TF-IDF + logistic regression** | **{test["accuracy"]:.3f}** | **{test["macro_f1"]:.3f}** | **{es["model"]["macro_f1"]:.3f}** | **{pt["model"]["macro_f1"]:.3f}** |

Calibration error {test["ece"]:.2f}; at the confidence threshold the model covers
{100 * test["confident_coverage"]:.0f}% of messages with {100 * test["confident_accuracy"]:.0f}% accuracy.
"""


def rescored(data: dict, cases: dict[str, dict]) -> tuple[list[dict], dict]:
    """The run's replies judged again with the current cases and scoring code."""
    runs = [
        judge(r, cases[r["id"]]) | {"repeat": r.get("repeat", 0)}
        for r in data["runs"]
        if not r["error"]
    ]
    return runs, summarize(runs, cases)


def render(datasets: list[dict]) -> str:
    spec = yaml.safe_load((HERE / "cases.yaml").read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in spec["cases"]}
    data = datasets[-1]
    runs, final = rescored(data, cases)
    meta = data["meta"]
    languages = {
        LANGS[lang]: summarize(group, cases)
        for lang, group in by(runs, lambda r: r["lang"]).items()
    }
    LABELS = ["before fixes", "after fixes", "with knowledge search", "final"]
    if len(datasets) > 1:
        scored = [rescored(d, cases) for d in datasets]
        first_runs = scored[0][0]
        summaries = {
            f"Run {i + 1} · all ({LABELS[i] if i < len(LABELS) else 'later'})": summary
            for i, (_, summary) in enumerate(scored)
        } | {f"Run {len(datasets)} · {name}": s for name, s in languages.items()}
        before = (
            "## What the first run found\n\n"
            "Run 1 is the agent before any change. The failures below led to the fixes in "
            "[Findings and fixes](#findings-and-fixes); run 2 repeats the same frozen cases after them.\n\n"
            + failures(first_runs, cases)
            + "\n"
        )
    else:
        first_runs, summaries = [], {"All": final} | languages
        before = ""
    reading_note = (
        "> **How to read the runs.** Run 1 is the held-out measurement: the agent as it was, on cases "
        "written without looking at it. Run 2 repeats the *same* cases after fixes made looking at run 1's "
        "failures, so it is **no longer held-out for those fixes**: it shows that the fixes work, not how "
        "the agent will do on new situations. "
        + (
            "Run 3 repeats them again after adding the knowledge search (decision 32): a regression check "
            "of the final system, not a new estimate. "
            if len(datasets) > 2
            else ""
        )
        + (
            "Run 4 is the final system (language reminder, 90-day transaction window): the same check. "
            if len(datasets) > 3
            else ""
        )
        + "Quote run 1 as the honest estimate."
        if len(datasets) > 1
        else ""
    )
    findings_path = HERE / "FINDINGS.md"
    findings = (
        findings_path.read_text(encoding="utf-8")
        if findings_path.exists() and len(datasets) > 1
        else ""
    )
    corrections = "\n".join(f"* `{c['case']}`: {c['what']}" for c in spec.get("corrections", []))
    corrections = (
        "\n### Scoring corrections made after run 1\n"
        "A scorer bug is fixed by re-scoring the stored replies, never by re-running until it passes:\n"
        + corrections
        + "\n"
        if corrections
        else ""
    )
    n_cases = {
        lang: len({r["id"] for r in group}) for lang, group in by(runs, lambda r: r["lang"]).items()
    }
    errors = data["errors"]
    return f"""# Held-out evaluation report

Run on {meta["date"]} · code `{meta["commit"]}`{" (with uncommitted changes)" if meta["dirty"] else ""} · model `{meta["model"]}` · {meta["repeats"]} repetitions of every case.
Generated by `evals/report/run_report.py` and `render.py`: the numbers below are the run's, not typed by hand.

## What was evaluated

The whole agent as deployed (the account chat with its tools, identity verification in the chat,
handoff to a person, the public assistant outside the login), through the real LangGraph graph
and the real model (Amazon Bedrock, Claude Haiku 4.5), on **{len({r["id"] for r in runs})} cases**
({n_cases.get("es", 0)} Spanish, {n_cases.get("pt", 0)} Portuguese), each run {meta["repeats"]} times
to see the model's variation: **{len(runs)} runs**.

| Kind | What a good run does |
|---|---|
| account | answers from the customer's own data, with the right figures, reading the right tool |
| public | answers hours, branches or how to open an account (visitor outside the login) |
| verification | verifies the customer in the chat (document, date of birth, code) and then answers |
| ambiguous | asks one question, reads nothing, does not hand over |
| handoff | hands over to a person (fraud, lost card, dispute, complaint, asks for a person) with the right reason |
| unsupported | does not claim it did a transfer, block, loan or change; explains or hands over |
| unsafe | prompt injection, another customer's data, skipping verification, leaking instructions, secrets shared by the customer |

### Data used (labeled)
| Data | Origin |
|---|---|
| Customer messages (all cases) | **Team-generated, synthetic**: written for this evaluation by the team with Claude's help, after the agent was built, with phrasings different from the development sets |
| Customers and accounts | **Synthetic fixtures** (`demo-001` Miguel, Colombia, COP; `demo-002` Ana, Argentina, ARS) |
| Organizers' dataset | Synthetic by construction. **Not used by this set**; it backs the deployed demo and the FCR rates of the intent model |
| Real customer data | **None** |

### Definitions
* **Safe automated resolution**: of the cases that a good agent resolves alone, the share that were resolved alone, with the right facts and no unsafe outcome.
* **Containment**: share of conversations where no person took over. **Safe containment** counts only the cases that needed no person (not the ones that must or may be handed over), and only when nothing went wrong, so a contained-but-wrong conversation does not count.
* **Escalation quality**: recall (handed over when it should), precision (handovers that were needed: cases that must be handed over, or ask for an action the bot cannot do), the reason given, and whether the case for the human is complete (the verified facts come from the session in code, the evidence from the tools actually run, a summary).
* **Unsafe outcome**: any of the six types in the table below, detected in code on every reply, not by a model.
* **Latency** is per customer message, measured around the agent and the model, **not** including CloudFront, the Lambda or DynamoDB. **Cost** is from the tokens Bedrock reported, at ${meta["price_per_mtok"]["input"]:.0f} / ${meta["price_per_mtok"]["output"]:.0f} per million input / output tokens.
* Rates come with a 95% Wilson interval in brackets: with few cases, the interval matters more than the point.

## Results

{headline(summaries)}

{reading_note}
{corrections}

### By kind of case (final run)
{by_kind(runs)}

### Unsafe outcomes by type
{unsafe_table(summaries)}

### Failures of the final run
{failures(runs, cases)}

{before}
{findings}

{"**Runs that errored (provider errors, left out of the numbers): " + ", ".join(errors) + "**" if errors else "No run errored."}

{ml_section()}
## Limitations (read before trusting the numbers)
* **The cases were written by the team, and by the same people (with Claude) who wrote the prompts.** Held-out means they were not used to develop or tune anything, not that they are independent. Real customers phrase things we did not think of.
* **Small sets.** {len({r["id"] for r in runs})} cases with {meta["repeats"]} repetitions: the repetitions measure the model's variation, not new situations. The intervals show how little a few cases can prove.
* **Two fictitious customers with small accounts.** The deployed demo reads the full synthetic dataset (5 million items); this set uses fixtures so every figure can be checked exactly.
* **Portuguese is written by the team, and the dataset has no Brazilian customers**: Portuguese conversations use the same fixtures (an Argentine and a Colombian customer writing in Portuguese).
* **Latency is the agent's, not the end to end.** The deployed latency (CloudFront, Lambda, DynamoDB) was measured separately with the load test (`evals/load`).
* **Faithfulness checks grounding, not correctness**: a figure that exists in the data but belongs to another row still counts as supported (see `docs/decisions.md`, decision 28).
* The fixtures' "today" is the dataset's last day (2026-06-17).

## Reproduce
```bash
cd backend
LLM_PROVIDER=bedrock AWS_PROFILE=hackathon uv run python ../evals/report/run_report.py --repeats {meta["repeats"]}
uv run python ../evals/report/render.py ../evals/report/results/run1.json ../evals/report/results/run2.json
```
The scoring code (`evals/report/metrics.py`) has its own tests (`uv run pytest -k report_metrics`).
"""


if __name__ == "__main__":
    sources = [json.loads(Path(arg).read_text(encoding="utf-8")) for arg in sys.argv[1:]]
    out = HERE / "REPORT.md"
    out.write_text(render(sources), encoding="utf-8")
    print(f"wrote {out}")
