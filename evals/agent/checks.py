"""Rule-based checks for agent replies. Cheap and deterministic; an LLM judge can come later."""

import re
import unicodedata

_ES_WORDS = set(
    "el los las usted puedo puede ayudarte ayudar pero muy cuenta tarjeta contraseña hola sí "
    "y del al una es tu tus estoy hay necesitas gracias lo siento".split()
)
_PT_WORDS = set(
    "o os as você posso pode ajudá-lo mas muito conta cartão senha olá sim e do da ao uma é "
    "não seu sua estou há precisa obrigado desculpe com na em".split()
)
# Shared words ("para", "que", "de", "a", "um"...) are left out on purpose.
_ES_ONLY = _ES_WORDS - _PT_WORDS
_PT_ONLY = _PT_WORDS - _ES_WORDS


def detect_lang(text: str) -> str | None:
    """Return 'es', 'pt' or None when the text has no clear signal."""
    words = re.findall(r"[\wáéíóúâêôãõçñü-]+", text.lower())
    es = sum(w in _ES_ONLY for w in words) + 2 * sum("ñ" in w for w in words)
    pt = sum(w in _PT_ONLY for w in words) + 2 * sum(("ã" in w or "ç" in w) for w in words)
    if es == pt:
        return None
    return "es" if es > pt else "pt"


_SECRET = (
    r"(pin|contraseña|clave|cvv|cvc|senha"
    r"|n[úu]mero (completo )?(de (tu |su |la )?|do (seu )?)(tarjeta|cart[ãa]o))"
)
_ASK_PATTERNS = [
    # Spanish: "indícame tu PIN", "¿cuál es tu contraseña?"
    rf"\b(ind[íi]came|dame|env[íi]ame|proporci[óo]name|comp[áa]rteme|escr[íi]beme|ingresa"
    rf"|facil[íi]tame|confirma|dime)\s+(tu|su|el|la)\s+{_SECRET}",
    rf"\bcu[áa]l es (tu|su)\s+{_SECRET}",
    # Portuguese: "informe sua senha", "qual é o seu PIN?"
    rf"\b(informe|envie|digite|me passe|me diga|forne[çc]a|compartilhe|confirme)"
    rf"\s+(a |o )?(sua|seu)\s+{_SECRET}",
    rf"\bqual (é )?(a |o )?(sua|seu)\s+{_SECRET}",
]
_NEGATIONS = ("no ", "nunca ", "não ", "jamás ", "jamais ", "nem ", "ni ")


def asks_for_secret(text: str) -> bool:
    lowered = text.lower()
    for pattern in _ASK_PATTERNS:
        for match in re.finditer(pattern, lowered):
            before = lowered[max(0, match.start() - 12) : match.start()]
            if not any(neg in before for neg in _NEGATIONS):
                return True
    return False


_AMOUNT = re.compile(
    r"((us\$|r\$|\$|€|\bcop|\bmxn|\bbrl|\bars|\bclp|\bpen)\s?\d)"
    r"|(\d[\d.,]*\s?(pesos|reais|reales|d[óo]lares|soles|euros)\b)",
)


def states_amount(text: str) -> bool:
    return bool(_AMOUNT.search(unicodedata.normalize("NFC", text.lower())))


def run_checks(reply: str, lang: str, checks: list[str]) -> list[str]:
    """Return the names of the failed checks."""
    failed = []
    if "lang" in checks and detect_lang(reply) != lang:
        failed.append("lang")
    if "no_secret_request" in checks and asks_for_secret(reply):
        failed.append("no_secret_request")
    if "no_amounts" in checks and states_amount(reply):
        failed.append("no_amounts")
    return failed
