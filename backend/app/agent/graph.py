"""LangGraph graph for the chat agent.

START -> route -> respond (model) -> END
                            └─ asks to verify ─> auth_gate -> END
               -> auth_gate (a verification step is pending: the model is skipped) -> END

Security steps are enforced here, in code: identity verification lives in auth_gate
(app/agent/identity.py), and the model can only ask for it.
"""

from functools import cache
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent import identity
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


def _with_verification_tool(model: BaseChatModel) -> BaseChatModel:
    try:
        return model.bind_tools([identity.start_identity_verification])
    except NotImplementedError:  # simple fakes in tests: they just never ask to verify
        return model


def build_graph(
    model: BaseChatModel,
    checkpointer: BaseCheckpointSaver | None = None,
    verifier: identity.IdentityVerifier | None = None,
) -> CompiledStateGraph:
    verifier = verifier or default_verifier()
    model_with_tool = _with_verification_tool(model)

    def route(state: ChatState) -> str:
        # A pending verification step consumes the message in code: the model never sees it.
        return "auth_gate" if identity.in_progress(state.get("auth")) else "respond"

    async def respond(state: ChatState, config: RunnableConfig) -> dict:
        # The system prompt is added per turn (not stored), so a language switch applies at once.
        auth, lang = state.get("auth"), state["lang"]
        prompt = system_prompt(lang)
        if identity.is_verified(auth, verifier.now()):
            prompt += "\n\n" + identity.verified_context(auth, lang)
            llm = model  # already verified: nothing to start
        else:
            llm = model_with_tool
        reply = await llm.ainvoke([SystemMessage(prompt), *state["messages"]], config)
        return {"messages": [reply]}

    def after_respond(state: ChatState) -> str:
        calls = getattr(state["messages"][-1], "tool_calls", None) or []
        return "auth_gate" if any(c["name"] == identity.VERIFY_TOOL for c in calls) else END

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
    # TODO(tools): account data tools, callable only when identity.is_verified(state["auth"]).
    # TODO(handoff): hand over to a human with a summary for ambiguous or high-risk cases.
    graph.add_node("respond", respond)
    graph.add_node("auth_gate", auth_gate)
    graph.add_conditional_edges(START, route, ["auth_gate", "respond"])
    graph.add_conditional_edges("respond", after_respond, ["auth_gate", END])
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
