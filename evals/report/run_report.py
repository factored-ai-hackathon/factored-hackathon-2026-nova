"""Held-out evaluation: runs evals/report/cases.yaml through the real agent and measures the
challenge's metrics (safe automated resolution, containment, escalation quality, unsafe
outcomes, p50/p95 latency and cost per case, by language). Writes results/<name>.json and
REPORT.md (see render.py).

From backend/:
    # live, the numbers that go in the report (Bedrock, costs cents):
    LLM_PROVIDER=bedrock AWS_PROFILE=hackathon \
        uv run python ../evals/report/run_report.py --repeats 3
    # offline, only checks the harness (the fake model is not what is being measured):
    uv run python ../evals/report/run_report.py --offline --repeats 1 --name offline

Cases run one after the other, so latency is not inflated by our own concurrency.
"""

import argparse
import asyncio
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "backend"))

from metrics import detect_lang, judge, summarize  # noqa: E402

from app import agent  # noqa: E402
from app.agent import Notice, TokenUsage, faithfulness, public  # noqa: E402
from app.agent.account_data import DemoAccountData  # noqa: E402
from app.agent.graph import build_graph  # noqa: E402
from app.agent.handoff import InMemoryCaseStore  # noqa: E402
from app.agent.identity import DEMO_CUSTOMERS, SESSION_CUSTOMER  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.llm import model_id  # noqa: E402
from app.sessions import get_session_store  # noqa: E402

NAMES = {c.customer_id: c.first_name for c in DEMO_CUSTOMERS}
RETRIES = 1  # one retry on a provider error (throttling); a second failure is recorded


class SpyData(DemoAccountData):
    """The demo accounts, remembering which customer's data was read through which tool."""

    def __init__(self):
        super().__init__()
        self.reads: list[tuple[str, str]] = []

    async def products(self, customer_id):
        self.reads.append(("get_my_products", customer_id))
        return await super().products(customer_id)

    async def transactions(self, customer_id, since, until):
        self.reads.append(("get_my_transactions", customer_id))
        return await super().transactions(customer_id, since, until)

    async def complaints(self, customer_id):
        self.reads.append(("get_my_complaints", customer_id))
        return await super().complaints(customer_id)


def make_model(offline: bool):
    if offline:
        from app.fake_llm import OfflineChatModel

        return OfflineChatModel(delay_seconds=0)
    from app.llm import get_chat_model

    return get_chat_model()


def initial_auth(case: dict) -> dict:
    customer = case.get("customer")
    if case["session"] == "verified":
        return {
            "step": "verified",
            SESSION_CUSTOMER: customer,
            "customer_id": customer,
            "first_name": NAMES[customer],
            "verified_until": time.time() + 900,
        }
    if case["session"] == "public":
        return public.public_auth()
    return {}  # anonymous: must verify in the chat


async def run_once(case: dict, model, price_in: float, price_out: float) -> dict:
    get_session_store.cache_clear()
    spy, cases = SpyData(), InMemoryCaseStore()
    agent._graph = build_graph(model, account_data=spy, case_store=cases)
    public.set_public_model(model)
    store = get_session_store()
    session = await store.create(case["lang"], initial_auth(case))
    stream = public.stream_public_reply if case["kind"] == "public" else agent.stream_reply

    said_list = case.get("turns") or [case["say"]]
    replies, said, turn_ms, first_ms, otp = [], [], [], [], None
    in_tokens = out_tokens = 0
    for said_text in said_list:
        text_in = said_text.replace("{otp}", otp or "")
        usage, started, first, reply = TokenUsage(), time.perf_counter(), None, ""
        async for piece in stream(session.id, text_in, case["lang"], usage):
            if isinstance(piece, Notice):
                if m := re.search(r"\d{6}", piece.text):
                    otp = m.group()
                continue
            if first is None and piece:
                first = round((time.perf_counter() - started) * 1000)
            reply += piece
        turn_ms.append(round((time.perf_counter() - started) * 1000))
        first_ms.append(first)
        replies.append(reply)
        said.append(text_in)
        in_tokens += usage.input_tokens or 0
        out_tokens += usage.output_tokens or 0

    final = await store.get(session.id)
    evidence = (final.case or {}).get("evidence", [])
    score = None
    if evidence:
        transcript = [{"role": "assistant", "text": replies[-1]}]
        score = faithfulness.analyze(transcript, evidence, NAMES.get(case.get("customer")))[
            "overall"
        ]
    return {
        "id": case["id"],
        "lang": case["lang"],
        "kind": case["kind"],
        "expect": case["expect"],
        "said": said,
        "replies": replies,
        "reads": spy.reads,
        "opened": await cases.list_recent(),
        "step": (final.auth or {}).get("step", "none"),
        "intent": ((final.case or {}).get("intent") or {}).get("label"),
        "language": detect_lang(replies[-1]) if replies else None,
        "turn_ms": turn_ms,
        "first_token_ms": first_ms,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "cost_usd": (in_tokens * price_in + out_tokens * price_out) / 1_000_000,
        "faithfulness": score,
        "error": None,
    }


async def run_case(case: dict, model, prices) -> dict:
    error = None
    for attempt in range(RETRIES + 1):
        try:
            return await run_once(case, model, *prices)
        except Exception as exc:  # provider errors: recorded, never hidden
            error = f"{type(exc).__name__}: {exc}"[:300]
            await asyncio.sleep(2 * (attempt + 1))
    return {
        "id": case["id"], "lang": case["lang"], "kind": case["kind"], "expect": case["expect"],
        "said": [], "replies": [], "reads": [], "opened": [], "step": "none", "intent": None,
        "language": None, "turn_ms": [], "first_token_ms": [], "input_tokens": 0,
        "output_tokens": 0, "cost_usd": 0.0, "faithfulness": None, "error": error,
    }  # fmt: skip


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, cwd=HERE, check=True
        ).stdout.strip()
    except Exception:
        return ""


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--only", help="comma separated case ids")
    parser.add_argument("--lang", choices=["es", "pt"])
    parser.add_argument("--name", default=datetime.now(UTC).strftime("%Y%m%d-%H%M"))
    args = parser.parse_args()

    all_cases = yaml.safe_load((HERE / "cases.yaml").read_text(encoding="utf-8"))["cases"]
    chosen = [
        c
        for c in all_cases
        if (not args.only or c["id"] in args.only.split(","))
        and (not args.lang or c["lang"] == args.lang)
    ]
    settings = get_settings()
    prices = (settings.llm_price_input_per_mtok, settings.llm_price_output_per_mtok)
    model = make_model(args.offline)
    by_id = {c["id"]: c for c in all_cases}

    runs = []
    total = len(chosen) * args.repeats
    for repeat in range(args.repeats):
        for case in chosen:
            run = await run_case(case, model, prices)
            runs.append({**judge(run, case), "repeat": repeat})
            mark = "ok " if runs[-1]["passed"] else "FAIL"
            print(f"[{len(runs)}/{total}] {mark} {case['id']} r{repeat}", flush=True)
    agent._graph = None
    public.set_public_model(None)

    result = {
        "meta": {
            "date": datetime.now(UTC).isoformat(timespec="seconds"),
            "commit": git("rev-parse", "--short", "HEAD"),
            "dirty": bool(git("status", "--porcelain", "--", "backend", "frontend")),
            "model": "offline fake model" if args.offline else model_id(settings),
            "provider": "fake" if args.offline else settings.llm_provider,
            "repeats": args.repeats,
            "price_per_mtok": {"input": prices[0], "output": prices[1]},
            "data": "team-generated synthetic cases; fictitious customers (demo-001, demo-002)",
        },
        "summary": summarize([r for r in runs if not r["error"]], by_id),
        "errors": [r["id"] for r in runs if r["error"]],
        "runs": runs,
    }
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    path = out / f"{args.name}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    asyncio.run(main())
