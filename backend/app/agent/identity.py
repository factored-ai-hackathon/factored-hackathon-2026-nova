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

import hashlib
import hmac
import re
import secrets
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Protocol

from langchain_core.tools import tool

VERIFY_TOOL = "start_identity_verification"

Step = Literal[
    "none", "awaiting_document", "awaiting_birth_date", "awaiting_otp", "verified", "locked"
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
    phone_last4: str


class CustomerDirectory(Protocol):
    async def find_by_document(self, document_number: str) -> CustomerIdentity | None: ...
    async def find_by_id(self, customer_id: str) -> CustomerIdentity | None: ...


# Fictional customers for the demo (not from the dataset). demo-001 is the customer logged in to
# the NovaBank UI mock. Documented for the judges in docs/demo.md.
DEMO_CUSTOMERS = (
    CustomerIdentity("demo-001", "Miguel", "1020304050", date(1990, 5, 14), "0192"),
    CustomerIdentity("demo-002", "Ana", "12345678900", date(1985, 11, 2), "4471"),
)


class DemoCustomerDirectory:
    def __init__(self, customers: tuple[CustomerIdentity, ...] = DEMO_CUSTOMERS) -> None:
        self._by_document = {c.document_number: c for c in customers}
        self._by_id = {c.customer_id: c for c in customers}

    async def find_by_document(self, document_number: str) -> CustomerIdentity | None:
        return self._by_document.get(document_number)

    async def find_by_id(self, customer_id: str) -> CustomerIdentity | None:
        return self._by_id.get(customer_id)


# --- parsing ----------------------------------------------------------------------------------


def parse_document(text: str) -> str | None:
    """Digits of a document number written with or without dots, dashes or spaces."""
    match = re.search(r"\d[\d.\s-]{4,22}\d", text)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group())
    return digits if 6 <= len(digits) <= 15 else None


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


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c)).strip(" .!¡¿?")


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
        return AuthResult(text(lang, "start"), {"step": "awaiting_document", "failures": failures})

    async def handle(self, auth: dict, message: str, lang: str) -> AuthResult:
        """The customer answered a pending step. The message never reaches the model."""
        auth = dict(auth)
        if wants_to_cancel(message):
            return AuthResult(
                text(lang, "cancelled"), {"step": "none", "failures": auth.get("failures", 0)}
            )
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
        if customer is None or customer.birth_date != birth_date:
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

    def _fail(self, auth: dict, lang: str, *, restart: bool) -> AuthResult:
        failures = auth.get("failures", 0) + 1
        if failures >= self.max_attempts:
            return AuthResult(text(lang, "locked"), {"step": "locked", "failures": failures})
        left = self.max_attempts - failures
        if restart:
            return AuthResult(
                text(lang, "mismatch", left=left),
                {"step": "awaiting_document", "failures": failures},
            )
        auth["failures"] = failures
        return AuthResult(text(lang, "wrong_otp", left=left), auth)
