"""LangGraph graph for the chat agent.

START -> route -> respond (model) -> END
                    ▲       ├─ asks to verify (or for data before verifying) ─> auth_gate -> END
                    │       └─ verified, calls account tools ─> account_tools ─┐
                    └──────────────────────────────────────────────────────────┘
               -> auth_gate (a verification step is pending: the model is skipped) -> END

Every message the model sees is also classified in code (app/agent/intent.py, the learned
component): the conversation's intent goes into the case, and for the reasons a first contact
rarely solves (complaints, retention) the turn's prompt tells the model to offer a human sooner.

Questions about products and policies go through search_policies (app/agent/knowledge.py,
decision 32): the account_tools node runs it too, verified or not (the documents are not data).

Security steps are enforced here, in code: identity verification lives in auth_gate
(app/agent/identity.py), and the model can only ask for it. The account tools are bound only
when the session is verified, and account_tools runs them for the session's customer
(app/agent/account_tools.py): the model can't choose whose data it reads.
"""

import json
from functools import cache
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent import handoff, identity, intent, knowledge
from app.agent.account_data import AccountData, get_account_data
from app.agent.account_tools import ACCOUNT_TOOL_NAMES, ACCOUNT_TOOLS, run_account_tool
from app.config import get_settings

PROMPTS_DIR = Path(__file__).parent / "prompts"

# Added to the customer's latest message for the model only (never stored or shown): when the
# customer switches language mid-conversation, the earlier turns pull the model back to the old one
# (found in the production smoke test), and a reminder next to the question beats one at the top.
LANGUAGE_TAGS = {"es": "(Responde en español.)", "pt": "(Responda em português.)"}


@cache
def system_prompt(lang: str) -> str:
    return (PROMPTS_DIR / f"{lang}.md").read_text(encoding="utf-8")


class ChatState(MessagesState):
    lang: str
    auth: dict  # identity verification state (app/agent/identity.py)
    notices: list[str]  # out-of-band messages for the customer (the demo SMS)
    sensitive_input: bool  # the customer's message was a verification answer
    tool_rounds: int  # account tool calls answered this turn
    session_id: str
    case: dict  # human handoff state and the evidence gathered (app/agent/handoff.py)
    handoff_notice: str  # case id, when this turn handed the conversation over
    turn_intent: dict  # the classifier's reading of this turn's message (app/agent/intent.py)


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
    case_store: handoff.CaseStore | None = None,
) -> CompiledStateGraph:
    verifier = verifier or default_verifier()
    data = account_data or get_account_data()
    cases = case_store or handoff.get_case_store()
    as_of = get_settings().data_as_of_date
    # Handing over to a person is always possible, verified or not.
    # Questions about products and policies can be answered with or without verification: the
    # documents are not customer data (decision 32).
    model_with_verify = _with_tools(
        model,
        [
            identity.start_identity_verification,
            handoff.request_human_agent,
            knowledge.search_policies,
        ],
    )
    model_with_accounts = _with_tools(
        model, [*ACCOUNT_TOOLS, handoff.request_human_agent, knowledge.search_policies]
    )

    def route(state: ChatState) -> str:
        # An open case: the human handles the conversation, the model stays out.
        if handoff.is_open(state.get("case")):
            return "human_queue"
        # A pending verification step consumes the message in code: the model never sees it.
        return "auth_gate" if identity.in_progress(state.get("auth")) else "respond"

    async def respond(state: ChatState, config: RunnableConfig) -> dict:
        # The system prompt is added per turn (not stored), so a language switch applies at once.
        auth, lang = state.get("auth"), state["lang"]
        prompt = system_prompt(lang)
        # The customer's latest message (after account tools the last message is a tool result).
        said = next((m.text for m in reversed(state["messages"]) if m.type == "human"), "")
        seen = intent.classify(said)
        if extra := intent.hint(seen, lang):
            prompt += "\n\n" + extra
        case = state.get("case") or {}
        case = {**case, "intent": intent.update(case.get("intent"), seen)}
        if identity.is_verified(auth, verifier.now()):
            prompt += "\n\n" + identity.verified_context(auth, lang, as_of)
            # Verified: the account tools, only for this customer (see account_tools).
            rounds = state.get("tool_rounds", 0)
            llm = model_with_accounts if rounds < MAX_TOOL_ROUNDS else model
        else:
            llm = model_with_verify if state.get("tool_rounds", 0) < MAX_TOOL_ROUNDS else model
        messages = list(state["messages"])
        last_human = next(
            (i for i in range(len(messages) - 1, -1, -1) if messages[i].type == "human"), None
        )
        if last_human is not None:
            tagged = f"{messages[last_human].text}\n\n{LANGUAGE_TAGS.get(lang, '')}".rstrip()
            messages[last_human] = HumanMessage(tagged)
        reply = await llm.ainvoke([SystemMessage(prompt), *messages], config)
        return {"messages": [reply], "case": case, "turn_intent": seen.as_dict()}

    def after_respond(state: ChatState) -> str:
        calls = getattr(state["messages"][-1], "tool_calls", None) or []
        if not calls:
            return END
        if any(c["name"] == handoff.HANDOFF_TOOL for c in calls):
            return "handoff"
        # Tools that can run now: the documents search always, the account tools once verified.
        runnable = {knowledge.SEARCH_TOOL_NAME}
        if identity.is_verified(state.get("auth"), verifier.now()):
            runnable |= ACCOUNT_TOOL_NAMES
        if all(c["name"] in runnable for c in calls):
            # Out of rounds (the model had no tools but still asked): end the turn.
            return "account_tools" if state.get("tool_rounds", 0) < MAX_TOOL_ROUNDS else END
        # Asked to verify, or asked for account data before verifying: verification first.
        return "auth_gate"

    async def account_tools(state: ChatState) -> dict:
        """Answer the model's account tool calls for the verified customer. The customer id comes
        from the session, never from the model's arguments."""
        auth = state.get("auth") or {}
        verified = identity.is_verified(auth, verifier.now())  # again: it may expire mid-turn
        case = state.get("case") or {}
        evidence = list(case.get("evidence", []))
        results, blocked = [], False
        for call in state["messages"][-1].tool_calls:
            if call["name"] == knowledge.SEARCH_TOOL_NAME:
                content = await knowledge.run_search(call.get("args") or {}, state["lang"])
                results.append(ToolMessage(content, tool_call_id=call["id"], name=call["name"]))
                evidence.append(
                    handoff.evidence_entry(call["name"], call.get("args") or {}, content)
                )
                continue
            if not verified:
                blocked = True
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
            evidence.append(handoff.evidence_entry(call["name"], call.get("args") or {}, content))
        rounds = state.get("tool_rounds", 0) + 1
        return {
            "messages": results,
            "tool_rounds": MAX_TOOL_ROUNDS if blocked else rounds,
            "case": {**case, "evidence": evidence[-handoff.MAX_EVIDENCE :]},
        }

    async def handoff_node(state: ChatState) -> dict:
        """Open a case for a human agent: the model's summary plus facts and evidence from code."""
        call = next(
            c for c in state["messages"][-1].tool_calls if c["name"] == handoff.HANDOFF_TOOL
        )
        auth, case_state = state.get("auth") or {}, state.get("case") or {}
        transcript = [
            {"role": "customer" if m.type == "human" else "assistant", "text": m.text}
            for m in state["messages"][:-1]
            if m.type in ("human", "ai") and m.text
        ]
        new_case = handoff.build_case(
            session_id=state.get("session_id", ""),
            lang=state["lang"],
            args=call.get("args") or {},
            auth=auth,
            evidence=case_state.get("evidence", []),
            transcript=transcript,
            verified=identity.is_verified(auth, verifier.now()),
            intent=case_state.get("intent"),
        )
        await cases.create(new_case)
        case_id = new_case["case_id"]
        return {
            "messages": [AIMessage(handoff.text(state["lang"], "handed_over", case_id=case_id))],
            "case": {
                **case_state,
                "handoff": {"case_id": case_id, "status": "waiting"},
                "last_case_id": case_id,
            },
            "handoff_notice": case_id,
        }

    async def human_queue(state: ChatState) -> dict:
        """A case is open: the customer's message goes to the human agent, not the model."""
        case_state = state.get("case") or {}
        case_id = case_state["handoff"]["case_id"]
        stored = await cases.add_message(case_id, "customer", state["messages"][-1].text)
        lang = state["lang"]
        if stored is None or stored["status"] not in handoff.OPEN_STATUSES:
            # Closed meanwhile: back to the bot from the next message.
            closed = {**case_state, "handoff": None}
            return {
                "messages": [AIMessage(handoff.text(lang, "closed", case_id=case_id))],
                "case": closed,
            }
        if stored["status"] == "waiting":
            return {"messages": [AIMessage(handoff.text(lang, "queued", case_id=case_id))]}
        return {"messages": []}  # an agent is on it: their reply comes through the console

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
    graph.add_node("respond", respond)
    graph.add_node("auth_gate", auth_gate)
    graph.add_node("account_tools", account_tools)
    graph.add_node("handoff", handoff_node)
    graph.add_node("human_queue", human_queue)
    graph.add_conditional_edges(START, route, ["auth_gate", "respond", "human_queue"])
    graph.add_conditional_edges(
        "respond", after_respond, ["auth_gate", "account_tools", "handoff", END]
    )
    graph.add_edge("account_tools", "respond")
    graph.add_edge("auth_gate", END)
    graph.add_edge("handoff", END)
    graph.add_edge("human_queue", END)
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
