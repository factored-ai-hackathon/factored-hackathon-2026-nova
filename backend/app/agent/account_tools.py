"""Tools the model can call about the verified customer's own accounts (decision 26).

The model only sees these schemas once the session is verified, and none of them takes a
customer id: run_account_tool gets it from the verified session state, so a prompt can't ask for
someone else's data. Results are compact JSON; response codes come with a plain reason so the
model doesn't have to guess what "51" means.
"""

import json
import unicodedata
from datetime import date, timedelta
from typing import Literal

from langchain_core.tools import tool

from app.agent.account_data import AccountData

MAX_TRANSACTIONS = 50
DEFAULT_DAYS = 90

# ISO 8583 response codes in the dataset.
DECLINE_REASONS = {
    "05": "do_not_honor (the bank declined it, e.g. a security rule)",
    "14": "invalid_card_number",
    "51": "insufficient_funds",
    "54": "expired_card",
}


@tool
def get_my_products() -> str:
    """The customer's products (accounts, cards, loans): type, last 4 digits, currency, balance,
    credit limit, status and days past due. Use it for balances, limits or product status."""
    return ""


@tool
def get_my_transactions(
    days: int = 90,
    status: Literal["all", "approved", "declined", "pending", "reversed"] = "all",
    search: str | None = None,
    limit: int = 20,
) -> str:
    """The customer's transactions, newest first, from the last `days` days (1-365) before
    the data date (default 90: when the customer names a month or no period, look back at least
    that far, or recent-looking results hide older ones). Filter by `status` (e.g. "declined" for
    rejected payments) and/or `search`
    (text in the merchant, category or type: Deposit, Withdrawal, Transfer, Payment, Purchase or
    Adjustment; Spanish or Portuguese words like "transferencia" or "compra" work too). Declined
    ones include the reason."""
    return ""


@tool
def get_my_complaints(status: Literal["all", "open", "closed"] = "all") -> str:
    """The customer's complaints and requests: category, dates, priority, status and whether
    the response time (SLA) was exceeded."""
    return ""


ACCOUNT_TOOLS = [get_my_products, get_my_transactions, get_my_complaints]
ACCOUNT_TOOL_NAMES = {t.name for t in ACCOUNT_TOOLS}

OPEN_COMPLAINT = {"open", "in process", "escalated"}


# The dataset's transaction types are English (Deposit, Withdrawal, Transfer, Payment, Purchase,
# Adjustment) while customers write Spanish or Portuguese: a search for "transferencia" has to
# find a Transfer. Keys are accent-free stems.
SEARCH_SYNONYMS = {
    "transferencia": "transfer", "transferir": "transfer",
    "deposito": "deposit", "depositar": "deposit",
    "retiro": "withdrawal", "retirada": "withdrawal", "saque": "withdrawal",
    "pago": "payment", "pagamento": "payment",
    "compra": "purchase",
    "ajuste": "adjustment",
}  # fmt: skip


def _plain_text(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    )


def _search_terms(text: str) -> list[str]:
    """The text as written, plus the English value it stands for (compra, compras -> purchase)."""
    plain = _plain_text(text).strip()
    terms = [plain]
    for stem, english in SEARCH_SYNONYMS.items():
        if plain.startswith(stem):
            terms.append(english)
    return terms


def _matches(row: dict, text: str) -> bool:
    haystack = _plain_text(
        " ".join(
            str(row.get(k, ""))
            for k in (
                "merchant_name",
                "merchant_category",
                "transaction_category",
                "transaction_type",
            )
        )
    )
    return any(term in haystack for term in _search_terms(text))


async def _transactions(data: AccountData, customer_id: str, as_of: date, args: dict) -> dict:
    days = min(max(int(args.get("days") or DEFAULT_DAYS), 1), 365)
    status = (args.get("status") or "all").lower()
    search = (args.get("search") or "").strip()
    limit = min(max(int(args.get("limit") or 20), 1), MAX_TRANSACTIONS)
    since = as_of - timedelta(days=days)
    rows = await data.transactions(customer_id, since, as_of)
    if status != "all":
        rows = [r for r in rows if str(r.get("transaction_status", "")).lower() == status]
    if search:
        rows = [r for r in rows if _matches(r, search)]
    for r in rows:
        if r.get("transaction_status") == "Declined" and r.get("response_code") in DECLINE_REASONS:
            r["decline_reason"] = DECLINE_REASONS[r["response_code"]]
    return {
        "period": {"from": since.isoformat(), "to": as_of.isoformat()},
        "total_found": len(rows),
        "transactions": rows[:limit],
    }


async def _complaints(data: AccountData, customer_id: str, args: dict) -> dict:
    rows = await data.complaints(customer_id)
    status = (args.get("status") or "all").lower()
    if status == "open":
        rows = [r for r in rows if str(r.get("status", "")).lower() in OPEN_COMPLAINT]
    elif status == "closed":
        rows = [r for r in rows if str(r.get("status", "")).lower() not in OPEN_COMPLAINT]
    return {"complaints": rows}


async def run_account_tool(
    name: str, args: dict, *, customer_id: str, data: AccountData, as_of: date
) -> str:
    """Run a tool for `customer_id` (from the verified session, never from `args`)."""
    try:
        if name == get_my_products.name:
            result: dict = {"products": await data.products(customer_id)}
        elif name == get_my_transactions.name:
            result = await _transactions(data, customer_id, as_of, args)
        elif name == get_my_complaints.name:
            result = await _complaints(data, customer_id, args)
        else:
            result = {"error": f"unknown tool {name}"}
    except (TypeError, ValueError) as e:
        result = {"error": f"invalid arguments: {e}"}
    result["data_as_of"] = as_of.isoformat()
    return json.dumps(result, ensure_ascii=False, default=str)
