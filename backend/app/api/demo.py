"""Demo panel: the test customers the judges log in with (docs/demo.md, decision 25).

The dataset is synthetic, so the panel shows what a person would know about themselves: the
document to log in with (plus the shared demo password) and the date of birth that Nova asks for
if the verification expires. Showing these grants nothing: logging in still needs the code sent
to the customer's phone (a demo SMS).
"""

import re
import secrets
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.agent.identity import CustomerDirectory, CustomerIdentity, get_customer_directory
from app.config import get_settings

router = APIRouter(prefix="/v1/demo", tags=["demo"])

CUSTOMER_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

Directory = Annotated[CustomerDirectory, Depends(get_customer_directory)]


class DemoCustomer(BaseModel):
    customer_id: str
    first_name: str
    country: str
    document_type: str
    document_number: str
    birth_date: date
    phone_last4: str


class Scenario(BaseModel):
    key: str  # "random", or a scenario from data/scripts/load_demo_data.py SCENARIOS
    customer: DemoCustomer


class ScenariosResponse(BaseModel):
    password: str
    scenarios: list[Scenario]


def _demo(customer: CustomerIdentity) -> DemoCustomer:
    return DemoCustomer(
        customer_id=customer.customer_id,
        first_name=customer.first_name,
        country=customer.country,
        document_type=customer.document_type,
        document_number=customer.document_number,
        birth_date=customer.birth_date,
        phone_last4=customer.phone_last4,
    )


@router.get("/scenarios")
async def scenarios(directory: Directory) -> ScenariosResponse:
    """One customer per scenario, picked at random among its candidates on every call."""
    index = await directory.demo_index()
    candidates = {"random": index.pool, **index.scenarios}
    found = []
    for key, ids in candidates.items():
        customer = await directory.find_by_id(secrets.choice(ids)) if ids else None
        if customer is not None:
            found.append(Scenario(key=key, customer=_demo(customer)))
    if not found:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "no_demo_customers")
    return ScenariosResponse(password=get_settings().demo_password, scenarios=found)


@router.get("/customers/{customer_id}")
async def demo_customer(customer_id: str, directory: Directory) -> DemoCustomer:
    """Any customer of the dataset, to check Nova's answers against it."""
    if not re.fullmatch(CUSTOMER_ID_PATTERN, customer_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_customer_id")
    customer = await directory.find_by_id(customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer_not_found")
    return _demo(customer)
