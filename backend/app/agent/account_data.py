"""The verified customer's own data: products, transactions and complaints (decision 26).

Read from the demo-customers table (data/scripts/load_demo_data.py), one partition per customer,
so every lookup is a single-partition Query: the customer_id comes from the verified session,
never from the model. Only the fields a customer would see in their banking app are returned
(no fraud labels or scores, no internal branch or agent ids).

"Today" is the end of the dataset (settings.data_as_of_date): the data is a snapshot.
"""

import asyncio
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any, Protocol

PRODUCT_FIELDS = (
    "product_type",
    "product_number_last4",
    "currency",
    "current_balance",
    "credit_limit",
    "interest_rate",
    "product_status",
    "days_past_due",
    "opening_date",
    "expiration_date",
    "last_transaction_at",
)
TRANSACTION_FIELDS = (
    "transaction_at",
    "transaction_type",
    "transaction_category",
    "amount",
    "currency",
    "channel",
    "merchant_name",
    "merchant_category",
    "transaction_city",
    "transaction_country",
    "transaction_status",
    "response_code",
    "product_id",
)
COMPLAINT_FIELDS = (
    "complaint_id",
    "created_at",
    "case_type",
    "category",
    "priority",
    "status",
    "sla_breached",
    "resolution_days",
)


def _pick(item: dict, fields: tuple[str, ...]) -> dict:
    return {k: _plain(item[k]) for k in fields if item.get(k) not in (None, "")}


def _plain(value: Any) -> Any:
    """DynamoDB numbers come back as Decimal: plain int/float for JSON."""
    from decimal import Decimal

    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


class AccountData(Protocol):
    async def products(self, customer_id: str) -> list[dict]: ...

    async def transactions(self, customer_id: str, since: date, until: date) -> list[dict]:
        """Newest first, with transaction_at between `since` and `until` (inclusive)."""
        ...

    async def complaints(self, customer_id: str) -> list[dict]: ...


class DynamoAccountData:
    def __init__(self, table: Any) -> None:
        self.table = table

    def _query(self, customer_id: str, condition: Any, newest_first: bool = False) -> list[dict]:
        from boto3.dynamodb.conditions import Key

        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("customer_id").eq(customer_id) & condition,
            "ScanIndexForward": not newest_first,
        }
        items: list[dict] = []
        while True:
            page = self.table.query(**kwargs)
            items.extend(page.get("Items", []))
            if "LastEvaluatedKey" not in page:
                return items
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def _products(self, customer_id: str) -> list[dict]:
        from boto3.dynamodb.conditions import Key

        items = self._query(customer_id, Key("sk").begins_with("PRODUCT#"))
        return [
            {"product_id": i["sk"].removeprefix("PRODUCT#"), **_pick(i, PRODUCT_FIELDS)}
            for i in items
        ]

    def _transactions(self, customer_id: str, since: date, until: date) -> list[dict]:
        from boto3.dynamodb.conditions import Key

        # Sort keys are TXN#<timestamp>#<id>: a key range is a date range.
        condition = Key("sk").between(f"TXN#{since.isoformat()}", f"TXN#{until.isoformat()}~")
        items = self._query(customer_id, condition, newest_first=True)
        return [_pick(i, TRANSACTION_FIELDS) for i in items]

    def _complaints(self, customer_id: str) -> list[dict]:
        from boto3.dynamodb.conditions import Key

        items = self._query(customer_id, Key("sk").begins_with("COMPLAINT#"))
        return [_pick(i, COMPLAINT_FIELDS) for i in items]

    async def products(self, customer_id: str) -> list[dict]:
        return await asyncio.to_thread(self._products, customer_id)

    async def transactions(self, customer_id: str, since: date, until: date) -> list[dict]:
        return await asyncio.to_thread(self._transactions, customer_id, since, until)

    async def complaints(self, customer_id: str) -> list[dict]:
        return await asyncio.to_thread(self._complaints, customer_id)


# --- fictional data for local development and tests (the demo customers in identity.py) ------


@dataclass
class DemoAccounts:
    products: list[dict]
    transactions: list[dict]  # any order
    complaints: list[dict]


DEMO_ACCOUNTS = {
    "demo-001": DemoAccounts(
        products=[
            {
                "product_id": "P-001",
                "product_type": "Cuenta Ahorro",
                "product_number_last4": "4521",
                "currency": "COP",
                "current_balance": 4850320.75,
                "product_status": "Active",
                "opening_date": "2021-03-15",
            },
            {
                "product_id": "P-002",
                "product_type": "Tarjeta Crédito",
                "product_number_last4": "2209",
                "currency": "COP",
                "current_balance": 1245800,
                "credit_limit": 10000000,
                "product_status": "Active",
                "days_past_due": 0,
                "expiration_date": "2028-09-30",
            },
        ],
        transactions=[
            {
                "transaction_at": "2026-06-15 19:42:10",
                "transaction_type": "Purchase",
                "transaction_category": "Food",
                "amount": 89000,
                "currency": "COP",
                "channel": "App",
                "merchant_name": "Rappi",
                "transaction_city": "Bogotá",
                "transaction_country": "Colombia",
                "transaction_status": "Approved",
                "response_code": "00",
                "product_id": "P-002",
            },
            {
                "transaction_at": "2026-06-12 10:05:00",
                "transaction_type": "Purchase",
                "transaction_category": "Other",
                "amount": 2350000,
                "currency": "COP",
                "channel": "POS",
                "merchant_name": "TecnoMundo",
                "transaction_city": "Medellín",
                "transaction_country": "Colombia",
                "transaction_status": "Declined",
                "response_code": "51",
                "product_id": "P-001",
            },
            {
                "transaction_at": "2026-05-02 08:30:00",
                "transaction_type": "Transfer",
                "amount": 500000,
                "currency": "COP",
                "channel": "Web",
                "transaction_status": "Approved",
                "response_code": "00",
                "product_id": "P-001",
            },
        ],
        complaints=[
            {
                "complaint_id": "Q-001",
                "created_at": "2026-06-13 09:00:00",
                "case_type": "Complaint",
                "category": "Transacción rechazada",
                "priority": "Media",
                "status": "In Process",
                "sla_breached": False,
            }
        ],
    ),
    "demo-002": DemoAccounts(
        products=[
            {
                "product_id": "P-101",
                "product_type": "Cuenta Corriente",
                "product_number_last4": "7788",
                "currency": "ARS",
                "current_balance": 125000.5,
                "product_status": "Active",
            }
        ],
        transactions=[
            {
                "transaction_at": "2026-06-10 12:00:00",
                "transaction_type": "Purchase",
                "transaction_category": "Food",
                "amount": 45200,
                "currency": "ARS",
                "channel": "POS",
                "merchant_name": "Mercado Sur",
                "transaction_city": "Rosario",
                "transaction_country": "Argentina",
                "transaction_status": "Approved",
                "response_code": "00",
                "product_id": "P-101",
            }
        ],
        complaints=[],
    ),
}


class DemoAccountData:
    def __init__(self, accounts: dict[str, DemoAccounts] = DEMO_ACCOUNTS) -> None:
        self.accounts = accounts

    def _get(self, customer_id: str) -> DemoAccounts:
        return self.accounts.get(customer_id, DemoAccounts([], [], []))

    async def products(self, customer_id: str) -> list[dict]:
        return [dict(p) for p in self._get(customer_id).products]

    async def transactions(self, customer_id: str, since: date, until: date) -> list[dict]:
        rows = [
            t
            for t in self._get(customer_id).transactions
            if since.isoformat() <= t["transaction_at"][:10] <= until.isoformat()
        ]
        return sorted((dict(t) for t in rows), key=lambda t: t["transaction_at"], reverse=True)

    async def complaints(self, customer_id: str) -> list[dict]:
        return [dict(c) for c in self._get(customer_id).complaints]


def build_account_data(settings: Any) -> AccountData:
    if settings.customer_directory == "dynamodb":
        import boto3

        table = boto3.resource("dynamodb", region_name=settings.aws_region).Table(
            settings.customers_table
        )
        return DynamoAccountData(table)
    return DemoAccountData()


@lru_cache
def get_account_data() -> AccountData:
    from app.config import get_settings

    return build_account_data(get_settings())
