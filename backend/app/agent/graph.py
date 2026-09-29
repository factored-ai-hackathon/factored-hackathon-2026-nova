"""LangGraph graph for the chat agent.

START -> route -> respond (model) -> END
                    ▲       ├─ asks to verify (or for data before verifying) ─> auth_gate -> END
                    │       └─ verified, calls account tools ─> account_tools ─┐
                    └──────────────────────────────────────────────────────────┘
               -> auth_gate (a verification step is pending: the model is skipped) -> END

Security steps are enforced here, in code: identity verification lives in auth_gate
(app/agent/identity.py), and the model can only ask for it. The account tools are bound only
when the session is verified, and account_tools runs them for the session's customer
(app/agent/account_tools.py): the model can't choose whose data it reads.
"""

import json
from functools import cache
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent import identity
from app.agent.account_data import AccountData, get_account_data
from app.agent.account_tools import ACCOUNT_TOOL_NAMES, ACCOUNT_TOOLS, run_account_tool
from app.config import get_settings

PROMPTS_DIR = Path(__file__).parent / "prompts"


@cache
def system_prompt(lang: str) -> str:
    return (PROMPTS_DIR / f"{lang}.md").read_text(encoding="utf-8")


class ChatState(MessagesState):
    lang: str
    auth: dict  # identity verification state (app/agent/identity.py)
    notices: list[str]  # out-of-band messages for the customer (the demo SMS)
    sensitive_input: bool  # the customer's message was a verification answer
    tool_rounds: int  # account tool calls answered this turn


# Account tool rounds per turn; after that the model has to answer with what it has.
MAX_TOOL_ROUNDS = 3


def _with_tools(model: BaseChatModel, tools: list) -> BaseChatModel:
    try:
        return model.bind_tools(tools)
    except NotImplementedError:  # simple fakes in tests: they just never call tools
        return model


def build_graph(
    model: BaseChatModel,
    checkpointer: BaseCheckpointSaver | None = None,
    verifier: identity.IdentityVerifier | None = None,
    account_data: AccountData | None = None,
) -> CompiledStateGraph:
    verifier = verifier or default_verifier()
    data = account_data or get_account_data()
    as_of = get_settings().data_as_of_date
    model_with_verify = _with_tools(model, [identity.start_identity_verification])
    model_with_accounts = _with_tools(model, ACCOUNT_TOOLS)

    def route(state: ChatState) -> str:
        # A pending verification step consumes the message in code: the model never sees it.
        return "auth_gate" if identity.in_progress(state.get("auth")) else "respond"

    async def respond(state: ChatState, config: RunnableConfig) -> dict:
        # The system prompt is added per turn (not stored), so a language switch applies at once.
        auth, lang = state.get("auth"), state["lang"]
        prompt = system_prompt(lang)
        if identity.is_verified(auth, verifier.now()):
            prompt += "\n\n" + identity.verified_context(auth, lang, as_of)
            # Verified: the account tools, only for this customer (see account_tools).
            rounds = state.get("tool_rounds", 0)
            llm = model_with_accounts if rounds < MAX_TOOL_ROUNDS else model
        else:
            llm = model_with_verify
        reply = await llm.ainvoke([SystemMessage(prompt), *state["messages"]], config)
        return {"messages": [reply]}

    def after_respond(state: ChatState) -> str:
        calls = getattr(state["messages"][-1], "tool_calls", None) or []
        if not calls:
            return END
        if identity.is_verified(state.get("auth"), verifier.now()) and all(
            c["name"] in ACCOUNT_TOOL_NAMES for c in calls
        ):
            # Out of rounds (the model had no tools but still asked): end the turn.
            return "account_tools" if state.get("tool_rounds", 0) < MAX_TOOL_ROUNDS else END
        # Asked to verify, or asked for account data before verifying: verification first.
        return "auth_gate"

    async def account_tools(state: ChatState) -> dict:
        """Answer the model's account tool calls for the verified customer. The customer id comes
        from the session, never from the model's arguments."""
        auth = state.get("auth") or {}
        verified = identity.is_verified(auth, verifier.now())  # again: it may expire mid-turn
        results = []
        for call in state["messages"][-1].tool_calls:
            if not verified:
                content = json.dumps({"error": "verification expired: the customer must verify"})
                results.append(ToolMessage(content, tool_call_id=call["id"], name=call["name"]))
                continue
            content = await run_account_tool(
                call["name"],
                call.get("args") or {},
                customer_id=auth["customer_id"],
                data=data,
                as_of=as_of,
            )
            results.append(ToolMessage(content, tool_call_id=call["id"], name=call["name"]))
        rounds = state.get("tool_rounds", 0) + 1
        return {"messages": results, "tool_rounds": rounds if verified else MAX_TOOL_ROUNDS}

    async def auth_gate(state: ChatState) -> dict:
        auth, lang = state.get("auth") or {}, state["lang"]
        if identity.in_progress(auth):
            result = await verifier.handle(auth, state["messages"][-1].text, lang)
        else:
            result = await verifier.start(auth, lang)
        return {
            "messages": [AIMessage(result.reply)],
            "auth": result.auth,
            "notices": result.notices,
            "sensitive_input": result.sensitive_input,
        }

    graph = StateGraph(ChatState)
    # TODO(answer_public): RAG over products and policies for public questions.
    # TODO(handoff): hand over to a human with a summary for ambiguous or high-risk cases.
    graph.add_node("respond", respond)
    graph.add_node("auth_gate", auth_gate)
    graph.add_node("account_tools", account_tools)
    graph.add_conditional_edges(START, route, ["auth_gate", "respond"])
    graph.add_conditional_edges("respond", after_respond, ["auth_gate", "account_tools", END])
    graph.add_edge("account_tools", "respond")
    graph.add_edge("auth_gate", END)
    # No checkpointer by default: stream_reply loads and saves the conversation through the session
    # store (DynamoDB when deployed), so the graph itself is stateless.
    return graph.compile(checkpointer=checkpointer)


def default_verifier() -> identity.IdentityVerifier:
    settings = get_settings()
    return identity.IdentityVerifier(
        identity.get_customer_directory(),
        max_attempts=settings.verification_max_attempts,
        otp_ttl_seconds=settings.otp_ttl_seconds,
        verified_ttl_seconds=settings.verified_ttl_minutes * 60,
    )
