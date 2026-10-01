# ruff: noqa: E501  (report text)
"""Does the learned component change what Nova does? An ablation of the intent hint (decision 29).

For complaints and retention the classifier tells Nova's prompt to offer a person in the same
reply. This runs the same messages through the real agent (Bedrock) with the hint ON and with it
OFF (the classifier still reads the message; only the hint is withheld) and compares what Nova
does: opens a case for a person, offers one, or neither. Control messages (anything else) show
whether the hint makes Nova offer a person where it is not needed.

From backend/:
    LLM_PROVIDER=bedrock AWS_PROFILE=hackathon PYTHONPATH=. \
        uv run python ../ml/intent/ablation.py --repeats 3

Writes ml/intent/ablation.json and prints the tables (also written to ml/intent/ABLATION.md).
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / "evals" / "report"))

from metrics import contains, percentile, rate  # noqa: E402

from app import agent  # noqa: E402
from app.agent import TokenUsage, intent  # noqa: E402
from app.agent.account_data import DemoAccountData  # noqa: E402
from app.agent.graph import build_graph  # noqa: E402
from app.agent.handoff import InMemoryCaseStore  # noqa: E402
from app.agent.identity import SESSION_CUSTOMER  # noqa: E402
from app.llm import get_chat_model  # noqa: E402
from app.sessions import get_session_store  # noqa: E402

OFFER_WORDS = ["asesor", "atendente", "humano", "persona"]
CUSTOMER = {"es": ("demo-001", "Miguel"), "pt": ("demo-002", "Ana")}
REAL_HINT = intent.hint


async def run_once(case: dict, model, hint_on: bool) -> dict:
    intent.hint = REAL_HINT if hint_on else (lambda *_: None)
    get_session_store.cache_clear()
    cases = InMemoryCaseStore()
    agent._graph = build_graph(model, account_data=DemoAccountData(), case_store=cases)
    customer_id, name = CUSTOMER[case["lang"]]
    auth = {
        "step": "verified", SESSION_CUSTOMER: customer_id, "customer_id": customer_id,
        "first_name": name, "verified_until": time.time() + 900,
    }  # fmt: skip
    session = await get_session_store().create(case["lang"], auth)
    usage, started = TokenUsage(), time.perf_counter()
    pieces = [p async for p in agent.stream_reply(session.id, case["say"], case["lang"], usage)]
    ms = round((time.perf_counter() - started) * 1000)
    reply = "".join(p for p in pieces if isinstance(p, str))
    opened = await cases.list_recent()
    offered = any(contains(reply, w) for w in OFFER_WORDS)
    seen = intent.classify(case["say"])
    return {
        "id": case["id"], "lang": case["lang"], "group": case["group"], "label": case["label"],
        "hint_on": hint_on, "predicted": seen.label, "fired": seen.early_handoff,
        "opened": bool(opened), "offered": offered and not opened,
        "reply_words": len(reply.split()), "ms": ms,
        "input_tokens": usage.input_tokens or 0, "output_tokens": usage.output_tokens or 0,
        "reply": reply,
    }  # fmt: skip


def outcome(r: dict) -> str:
    return "opened" if r["opened"] else "offered" if r["offered"] else "neither"


def table(rows: list[dict]) -> str:
    out = []
    for group, title in (("target", "Complaints and retention (the hint should help)"),
                         ("control", "Everything else (the hint should not matter)")):  # fmt: skip
        out += [f"### {title}\n", "| Hint | Runs | Opened a case | Offered a person | Either | Mean words | p50 time |",
                "|---|---|---|---|---|---|---|"]  # fmt: skip
        for on in (True, False):
            g = [r for r in rows if r["group"] == group and r["hint_on"] == on]
            either = rate(sum(r["opened"] or r["offered"] for r in g), len(g))
            ci = either["ci95"]
            out.append(
                f"| {'ON' if on else 'OFF'} | {len(g)} | {sum(r['opened'] for r in g)} "
                f"| {sum(r['offered'] for r in g)} | **{either['k']}/{either['n']} "
                f"({100 * either['rate']:.0f}%, CI {100 * ci[0]:.0f}-{100 * ci[1]:.0f})** "
                f"| {statistics.fmean(r['reply_words'] for r in g):.0f} "
                f"| {percentile([r['ms'] for r in g], 50) / 1000:.1f} s |"
            )
        out.append("")
    return "\n".join(out)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    cases = yaml.safe_load((HERE / "ablation.yaml").read_text(encoding="utf-8"))["cases"]
    model = get_chat_model()
    rows = []
    for repeat in range(args.repeats):
        for case in cases:
            for hint_on in (True, False):  # alternate, so drift in the service hits both alike
                rows.append({**await run_once(case, model, hint_on), "repeat": repeat})
            print(f"r{repeat} {case['id']}", flush=True)
    intent.hint = REAL_HINT
    agent._graph = None

    classifier = [r for r in rows if r["hint_on"] and r["repeat"] == 0]
    fired = {
        g: sum(r["fired"] for r in classifier if r["group"] == g) for g in ("target", "control")
    }
    sizes = {g: sum(r["group"] == g for r in classifier) for g in ("target", "control")}
    by_lang = {
        lang: {
            "target_hint_fired": sum(r["fired"] for r in classifier if r["group"] == "target" and r["lang"] == lang),
            "targets": sum(r["group"] == "target" and r["lang"] == lang for r in classifier),
        }
        for lang in ("es", "pt")
    }  # fmt: skip
    # Paired: the same message and repeat, hint ON against OFF.
    paired = {}
    for g in ("target", "control"):
        on = {(r["id"], r["repeat"]): r for r in rows if r["group"] == g and r["hint_on"]}
        off = {(r["id"], r["repeat"]): r for r in rows if r["group"] == g and not r["hint_on"]}
        either = lambda r: r["opened"] or r["offered"]  # noqa: E731
        paired[g] = {
            "only_with_hint": sum(either(on[k]) and not either(off[k]) for k in on),
            "only_without_hint": sum(either(off[k]) and not either(on[k]) for k in on),
            "same": sum(either(on[k]) == either(off[k]) for k in on),
        }
    summary = {"repeats": args.repeats, "classifier_fired": fired, "group_sizes": sizes,
               "by_language": by_lang, "paired": paired}  # fmt: skip
    (HERE / "ablation.json").write_text(
        json.dumps({"summary": summary, "runs": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    md = (
        "# Intent hint ablation (generated by ablation.py)\n\n"
        f"{len(cases)} messages x {args.repeats} repetitions x hint ON/OFF, through the real agent on Bedrock. "
        f"The classifier fires on {fired['target']}/{sizes['target']} target messages "
        f"(ES {by_lang['es']['target_hint_fired']}/{by_lang['es']['targets']}, "
        f"PT {by_lang['pt']['target_hint_fired']}/{by_lang['pt']['targets']}) and on "
        f"{fired['control']}/{sizes['control']} controls.\n\n{table(rows)}\n"
        f"Paired (same message and repetition, hint ON vs OFF): on target messages a person was "
        f"offered or opened only with the hint {paired['target']['only_with_hint']} times, only without it "
        f"{paired['target']['only_without_hint']} times, the same {paired['target']['same']}; on controls "
        f"{paired['control']['only_with_hint']} / {paired['control']['only_without_hint']} / {paired['control']['same']}.\n"
    )
    (HERE / "ABLATION.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    asyncio.run(main())
