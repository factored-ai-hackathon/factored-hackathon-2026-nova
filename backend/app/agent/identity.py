"""Identity verification: document number + date of birth (KBA), then a one-time code (OTP).

Enforced in code by the graph's auth_gate node. The model can only *ask* for verification (the
start_identity_verification tool); it never sees the customer's answers and can't mark anyone as
verified. While a step is pending, the customer's message goes straight to auth_gate, and it is
stored as a placeholder in the history and the interaction log.

Security choices:
- An unknown document number gets the same reply as a known one ("now your date of birth"), and a
  wrong date fails with the same message either way, so the flow can't be used to find out who is
  a customer.
- `max_attempts` failures (wrong data or wrong code) lock verification for the whole session.
- The code is stored hashed with a random salt, expires after `otp_ttl_seconds`, and is only shown
  through the delivery channel (in the demo, a `notice` event: there is no real SMS).
- Verification lasts `verified_ttl_seconds`; after that the customer has to verify again.
"""

import asyncio
import hashlib
import hmac
import re
import secrets
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any, Literal, Protocol

from langchain_core.tools import tool

VERIFY_TOOL = "start_identity_verification"

Step = Literal[
    "none",
    "awaiting_document",
    "awaiting_birth_date",
    "awaiting_otp",
    "awaiting_login_code",
    "verified",
    "locked",
]
IN_PROGRESS = ("awaiting_document", "awaiting_birth_date", "awaiting_otp")


@tool(VERIFY_TOOL)
def start_identity_verification() -> str:
    """Start verifying the customer's identity. Call it, without writing any other text, when the
    customer asks about their own accounts, balances, cards, transactions, transfers, loans,
    complaints or any other personal data, or asks to be verified. Never ask for their document,
    date of birth or codes yourself: this tool does it."""
    return "started"


# --- customers ------------------------------------------------------------------------------


@dataclass(frozen=True)
class CustomerIdentity:
    customer_id: str
    first_name: str
    document_number: str
    birth_date: date
    phone_last4: str  # empty: no mobile phone on file, so no code can be sent
    country: str = ""
    document_type: str = ""


@dataclass
class DemoIndex:
    """Who the demo login offers: a pool of random customers and the customers of each scenario
    (docs/demo.md). All of them have a mobile phone."""

    pool: list[str] = field(default_factory=list)
    scenarios: dict[str, list[str]] = field(default_factory=dict)


class CustomerDirectory(Protocol):
    async def find_by_document(self, document_number: str) -> CustomerIdentity | None:
        """`document_number` as normalize_document returns it."""
        ...

    async def find_by_id(self, customer_id: str) -> CustomerIdentity | None: ...
    async def demo_index(self) -> DemoIndex: ...


def normalize_document(text: str) -> str:
    """Letters and digits only, uppercase: passports have letters; dots and dashes don't count."""
    return re.sub(r"[^0-9A-Za-z]", "", text).upper()


# Fictional customers for local development and tests (not from the dataset). Documented in
# docs/demo.md. Deployed, the directory is the whole dataset (DynamoCustomerDirectory).
DEMO_CUSTOMERS = (
    CustomerIdentity(
        "demo-001", "Miguel", "1020304050", date(1990, 5, 14), "0192", "Colombia", "CC"
    ),
    CustomerIdentity("demo-002", "Ana", "30123456", date(1985, 11, 2), "4471", "Argentina", "DNI"),
)


class DemoCustomerDirectory:
    def __init__(self, customers: tuple[CustomerIdentity, ...] = DEMO_CUSTOMERS) -> None:
        self._by_document = {c.document_number: c for c in customers}
        self._by_id = {c.customer_id: c for c in customers}

    async def find_by_document(self, document_number: str) -> CustomerIdentity | None:
        return self._by_document.get(document_number)

    async def find_by_id(self, customer_id: str) -> CustomerIdentity | None:
        return self._by_id.get(customer_id)

    async def demo_index(self) -> DemoIndex:
        return DemoIndex(pool=list(self._by_id), scenarios={})


def _identity_from_item(item: dict) -> CustomerIdentity:
    return CustomerIdentity(
        customer_id=item["customer_id"],
        first_name=item["first_name"],
        document_number=item["document_number"],
        birth_date=date.fromisoformat(item["birth_date"]),
        phone_last4=item.get("phone_last4", ""),
        country=item.get("country", ""),
        document_type=item.get("document_type", ""),
    )


# Written by data/scripts/load_demo_data.py: the demo scenarios and a pool of random customers,
# so the demo login can offer them without scanning the table.
INDEX_KEY = {"customer_id": "#index", "sk": "DEMO_CUSTOMERS"}


class DynamoCustomerDirectory:
    """Customers loaded from the dataset into the demo-customers table (PROFILE items)."""

    def __init__(self, table: Any) -> None:
        self.table = table

    def _find_by_document(self, document_number: str) -> CustomerIdentity | None:
        from boto3.dynamodb.conditions import Key

        items = self.table.query(
            IndexName="by-document",
            KeyConditionExpression=Key("document_number").eq(document_number),
            Limit=1,
        ).get("Items", [])
        return _identity_from_item(items[0]) if items else None

    def _find_by_id(self, customer_id: str) -> CustomerIdentity | None:
        item = self.table.get_item(Key={"customer_id": customer_id, "sk": "PROFILE"}).get("Item")
        return _identity_from_item(item) if item else None

    def _demo_index(self) -> DemoIndex:
        item = self.table.get_item(Key=INDEX_KEY).get("Item") or {}
        scenarios = {k: list(v) for k, v in item.get("scenarios", {}).items()}
        return DemoIndex(pool=list(item.get("customer_ids", [])), scenarios=scenarios)

    async def find_by_document(self, document_number: str) -> CustomerIdentity | None:
        return await asyncio.to_thread(self._find_by_document, document_number)

    async def find_by_id(self, customer_id: str) -> CustomerIdentity | None:
        return await asyncio.to_thread(self._find_by_id, customer_id)

    async def demo_index(self) -> DemoIndex:
        return await asyncio.to_thread(self._demo_index)


def build_customer_directory(settings: Any) -> CustomerDirectory:
    if settings.customer_directory == "dynamodb":
        import boto3

        table = boto3.resource("dynamodb", region_name=settings.aws_region).Table(
            settings.customers_table
        )
        return DynamoCustomerDirectory(table)
    return DemoCustomerDirectory()


@lru_cache
def get_customer_directory() -> CustomerDirectory:
    from app.config import get_settings

    return build_customer_directory(get_settings())


# --- parsing ----------------------------------------------------------------------------------


def parse_document(text: str) -> str | None:
    """A document number written with or without dots, dashes or spaces ("1.020.304.050"), or a
    passport-style code with letters ("AB12345"), normalized (normalize_document)."""
    for word in re.findall(r"[0-9A-Za-z-]+", text):
        code = normalize_document(word)
        if 6 <= len(code) <= 15 and re.search(r"\d", code) and re.search(r"[A-Z]", code):
            return code
    if match := re.search(r"\d[\d.\s-]{4,22}\d", text):
        digits = re.sub(r"\D", "", match.group())
        if 6 <= len(digits) <= 15:
            return digits
    return None


def parse_birth_date(text: str) -> date | None:
    """DD/MM/YYYY (also with - or .) or YYYY-MM-DD."""
    try:
        if m := re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", text):
            return date(int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        return None
    return None


def parse_otp(text: str) -> str | None:
    match = re.search(r"\d{6}", re.sub(r"[\s-]", "", text))
    return match.group() if match else None


def normalize_text(text: str) -> str:
    """Lowercase, without accents or surrounding punctuation ("México" == "mexico")."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c)).strip(" .!¡¿?")


_normalize = normalize_text


CANCEL_WORDS = {"cancelar", "cancela", "cancel", "salir", "sair", "parar", "detener"}


def wants_to_cancel(text: str) -> bool:
    return _normalize(text) in CANCEL_WORDS


# Only used by the offline fake model (LLM_PROVIDER=fake) to imitate the real model's tool call.
# Security never depends on it: account data is released only after auth_gate verifies.
_ACCOUNT_WORDS = (
    "saldo",
    "movimiento",
    "mi cuenta",
    "mis cuentas",
    "mi tarjeta",
    "mis tarjetas",
    "transacci",
    "transferencia",
    "mi prestamo",
    "mi queja",
    "extracto",
    "verific",
    "minha conta",
    "minhas contas",
    "meu cartao",
    "meus cartoes",
    "transac",
    "extrato",
    "emprestimo",
)


def looks_like_account_request(text: str) -> bool:
    normalized = _normalize(text)
    return any(word in normalized for word in _ACCOUNT_WORDS)


# --- messages (fixed text, not the model: nothing to inject into) -----------------------------

TEXTS = {
    "es": {
        "start": "Para proteger tu información, primero necesito verificar tu identidad. "
        "Escribe tu número de documento, solo con números. Puedes escribir *cancelar* "
        "en cualquier momento.",
        "bad_document": "No reconocí un número de documento. Escríbelo solo con números, "
        "sin puntos ni espacios.",
        "ask_birth_date": "Gracias. Ahora escribe tu fecha de nacimiento (DD/MM/AAAA).",
        "bad_date": "No reconocí la fecha. Usa el formato DD/MM/AAAA, por ejemplo 14/05/1990.",
        "mismatch": "Los datos no coinciden con nuestros registros. Te quedan {left} "
        "intento(s). Escribe de nuevo tu número de documento.",
        "otp_sent": "Te enviamos un código de 6 dígitos por SMS al celular terminado en "
        "{last4}. Escríbelo aquí; vence en {minutes} minutos.",
        "otp_notice": "SMS (demo) al celular terminado en {last4}: tu código de verificación "
        "NovaBank es {code}",
        "bad_otp_format": "Escribe el código de 6 dígitos que te enviamos por SMS.",
        "wrong_otp": "El código no es correcto. Te quedan {left} intento(s).",
        "otp_expired": "El código venció. Te enviamos uno nuevo al celular terminado en {last4}.",
        "verified": "¡Listo, {name}! Verifiqué tu identidad. ¿En qué te ayudo?",
        "locked": "Por seguridad, bloqueé la verificación en esta conversación después de "
        "varios intentos fallidos. Si necesitas ayuda con tu cuenta, un asesor de nuestro "
        "centro de contacto puede atenderte.",
        "cancelled": "Cancelé la verificación. ¿En qué más te puedo ayudar?",
        "placeholder": "[dato de verificación]",
        "verified_context": "La identidad del cliente ya fue verificada: se llama {name}. "
        "Salúdalo por su nombre. Todavía no tienes herramientas para consultar sus productos: "
        "si te pide datos de sus cuentas, explícale que esa consulta aún no está disponible "
        "en este canal. Nunca inventes datos.",
    },
    "pt": {
        "start": "Para proteger suas informações, primeiro preciso verificar sua identidade. "
        "Digite o número do seu documento, só com números. Você pode escrever *cancelar* "
        "a qualquer momento.",
        "bad_document": "Não reconheci um número de documento. Digite só com números, "
        "sem pontos nem espaços.",
        "ask_birth_date": "Obrigado. Agora digite sua data de nascimento (DD/MM/AAAA).",
        "bad_date": "Não reconheci a data. Use o formato DD/MM/AAAA, por exemplo 14/05/1990.",
        "mismatch": "Os dados não conferem com nossos registros. Você tem mais {left} "
        "tentativa(s). Digite novamente o número do seu documento.",
        "otp_sent": "Enviamos um código de 6 dígitos por SMS para o celular terminado em "
        "{last4}. Digite aqui; ele vence em {minutes} minutos.",
        "otp_notice": "SMS (demo) para o celular terminado em {last4}: seu código de "
        "verificação NovaBank é {code}",
        "bad_otp_format": "Digite o código de 6 dígitos que enviamos por SMS.",
        "wrong_otp": "O código não está correto. Você tem mais {left} tentativa(s).",
        "otp_expired": "O código venceu. Enviamos um novo para o celular terminado em {last4}.",
        "verified": "Pronto, {name}! Verifiquei sua identidade. Como posso ajudar?",
        "locked": "Por segurança, bloqueei a verificação nesta conversa depois de várias "
        "tentativas sem sucesso. Se precisar de ajuda com sua conta, um atendente da nossa "
        "central pode ajudar.",
        "cancelled": "Cancelei a verificação. Em que mais posso ajudar?",
        "placeholder": "[dado de verificação]",
        "verified_context": "A identidade do cliente já foi verificada: o nome dele é {name}. "
        "Cumprimente-o pelo nome. Você ainda não tem ferramentas para consultar os produtos "
        "dele: se pedir dados das contas, explique que essa consulta ainda não está "
        "disponível neste canal. Nunca invente dados.",
    },
}


def text(lang: str, key: str, **values: Any) -> str:
    return TEXTS.get(lang, TEXTS["es"])[key].format(**values)


# --- state machine ------------------------------------------------------------------------------


# The customer logged in to the demo web session (set when the chat session is created). When
# present, only that customer can be verified in the conversation: someone logged in as Ana can't
# verify as Miguel even with his document, date of birth and code.
SESSION_CUSTOMER = "session_customer_id"


def session_auth(customer_id: str | None) -> dict:
    """Initial verification state of a chat session."""
    return {SESSION_CUSTOMER: customer_id} if customer_id else {}


def _keep_session(auth: dict, new: dict) -> dict:
    if SESSION_CUSTOMER in auth:
        new[SESSION_CUSTOMER] = auth[SESSION_CUSTOMER]
    return new


# The web login's code step (app/api/auth.py). Not IN_PROGRESS: the chat can't answer it.
LOGIN_STEP = "awaiting_login_code"
LoginOutcome = Literal["ok", "wrong_code", "expired", "locked"]


def in_progress(auth: dict | None) -> bool:
    return (auth or {}).get("step") in IN_PROGRESS


def is_verified(auth: dict | None, now: float | None = None) -> bool:
    auth = auth or {}
    now = time.time() if now is None else now
    return auth.get("step") == "verified" and auth.get("verified_until", 0) > now


def verified_context(auth: dict, lang: str) -> str:
    return text(lang, "verified_context", name=auth.get("first_name", ""))


@dataclass
class AuthResult:
    reply: str
    auth: dict
    notices: list[str] = field(default_factory=list)
    sensitive_input: bool = False  # the customer's message was a verification answer


def _hash(salt: str, code: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


class IdentityVerifier:
    def __init__(
        self,
        directory: CustomerDirectory,
        *,
        max_attempts: int = 3,
        otp_ttl_seconds: int = 300,
        verified_ttl_seconds: int = 1800,
        now: Callable[[], float] = time.time,
        new_code: Callable[[], str] = lambda: f"{secrets.randbelow(10**6):06d}",
    ) -> None:
        self.directory = directory
        self.max_attempts = max_attempts
        self.otp_ttl_seconds = otp_ttl_seconds
        self.verified_ttl_seconds = verified_ttl_seconds
        self.now = now
        self.new_code = new_code

    async def start(self, auth: dict | None, lang: str) -> AuthResult:
        """The model asked to verify: begin (or report that verification is locked)."""
        auth = dict(auth or {})
        if auth.get("step") == "locked":
            return AuthResult(text(lang, "locked"), auth)
        failures = auth.get("failures", 0)
        new = _keep_session(auth, {"step": "awaiting_document", "failures": failures})
        return AuthResult(text(lang, "start"), new)

    async def handle(self, auth: dict, message: str, lang: str) -> AuthResult:
        """The customer answered a pending step. The message never reaches the model."""
        auth = dict(auth)
        if wants_to_cancel(message):
            new = _keep_session(auth, {"step": "none", "failures": auth.get("failures", 0)})
            return AuthResult(text(lang, "cancelled"), new)
        step = auth.get("step")
        if step == "awaiting_document":
            result = await self._document(auth, message, lang)
        elif step == "awaiting_birth_date":
            result = await self._birth_date(auth, message, lang)
        else:
            result = await self._otp(auth, message, lang)
        result.sensitive_input = True
        return result

    async def _document(self, auth: dict, message: str, lang: str) -> AuthResult:
        document = parse_document(message)
        if document is None:
            return AuthResult(text(lang, "bad_document"), auth)
        customer = await self.directory.find_by_document(document)
        # Same answer whether or not the document exists (no customer enumeration).
        auth.update(
            step="awaiting_birth_date", candidate_id=customer.customer_id if customer else None
        )
        return AuthResult(text(lang, "ask_birth_date"), auth)

    async def _birth_date(self, auth: dict, message: str, lang: str) -> AuthResult:
        birth_date = parse_birth_date(message)
        if birth_date is None:
            return AuthResult(text(lang, "bad_date"), auth)
        candidate_id = auth.get("candidate_id")
        customer = await self.directory.find_by_id(candidate_id) if candidate_id else None
        bound = auth.get(SESSION_CUSTOMER)
        if (
            customer is None
            or customer.birth_date != birth_date
            # Right data, but not the logged-in customer: same answer as wrong data.
            or (bound is not None and customer.customer_id != bound)
        ):
            return self._fail(auth, lang, restart=True)
        auth.update(
            step="awaiting_otp",
            customer_id=customer.customer_id,
            first_name=customer.first_name,
            phone_last4=customer.phone_last4,
        )
        auth.pop("candidate_id", None)
        return self._send_code(auth, lang, "otp_sent")

    async def _otp(self, auth: dict, message: str, lang: str) -> AuthResult:
        if self.now() > auth.get("otp_expires_at", 0):
            return self._send_code(auth, lang, "otp_expired")
        code = parse_otp(message)
        if code is None:
            return AuthResult(text(lang, "bad_otp_format"), auth)
        if not hmac.compare_digest(_hash(auth["otp_salt"], code), auth["otp_hash"]):
            return self._fail(auth, lang, restart=False)
        for key in ("otp_hash", "otp_salt", "otp_expires_at", "phone_last4"):
            auth.pop(key, None)
        auth.update(
            step="verified", failures=0, verified_until=self.now() + self.verified_ttl_seconds
        )
        return AuthResult(text(lang, "verified", name=auth["first_name"]), auth)

    def _send_code(self, auth: dict, lang: str, key: str) -> AuthResult:
        code, salt = self.new_code(), secrets.token_hex(8)
        auth.update(
            otp_salt=salt,
            otp_hash=_hash(salt, code),
            otp_expires_at=self.now() + self.otp_ttl_seconds,
        )
        last4 = auth["phone_last4"]
        minutes = max(1, self.otp_ttl_seconds // 60)
        return AuthResult(
            text(lang, key, last4=last4, minutes=minutes),
            auth,
            notices=[text(lang, "otp_notice", last4=last4, code=code)],
        )

    # --- web login (document + password, then a code): app/api/auth.py ---------------------

    def start_login(self, customer: CustomerIdentity, lang: str) -> AuthResult:
        """The document and password were right: send the login code. The resulting state is the
        chat session's, so after the code the conversation starts verified (decision 26)."""
        auth = {
            "step": LOGIN_STEP,
            SESSION_CUSTOMER: customer.customer_id,
            "customer_id": customer.customer_id,
            "first_name": customer.first_name,
            "phone_last4": customer.phone_last4,
            "failures": 0,
        }
        return self._send_code(auth, lang, "otp_sent")

    def finish_login(self, auth: dict, code: str) -> tuple[LoginOutcome, dict]:
        """Check the login code. Any outcome but "wrong_code" ends the attempt."""
        auth = dict(auth)
        if auth.get("step") != LOGIN_STEP:
            return "expired", auth
        if self.now() > auth.get("otp_expires_at", 0):
            return "expired", {**auth, "step": "none"}
        if not hmac.compare_digest(_hash(auth["otp_salt"], code), auth["otp_hash"]):
            auth["failures"] = auth.get("failures", 0) + 1
            if auth["failures"] >= self.max_attempts:
                return "locked", {**auth, "step": "locked"}
            return "wrong_code", auth
        for key in ("otp_hash", "otp_salt", "otp_expires_at", "phone_last4"):
            auth.pop(key, None)
        auth.update(
            step="verified", failures=0, verified_until=self.now() + self.verified_ttl_seconds
        )
        return "ok", auth

    def _fail(self, auth: dict, lang: str, *, restart: bool) -> AuthResult:
        failures = auth.get("failures", 0) + 1
        if failures >= self.max_attempts:
            locked = _keep_session(auth, {"step": "locked", "failures": failures})
            return AuthResult(text(lang, "locked"), locked)
        left = self.max_attempts - failures
        if restart:
            return AuthResult(
                text(lang, "mismatch", left=left),
                _keep_session(auth, {"step": "awaiting_document", "failures": failures}),
            )
        auth["failures"] = failures
        return AuthResult(text(lang, "wrong_otp", left=left), auth)
