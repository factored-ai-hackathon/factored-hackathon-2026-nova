"""Faithfulness of Nova's answers to the data it consulted, for the agent console (decision 28).

For a handed-over case, each of Nova's answers is compared with the evidence (the account tool
results of that conversation):

- Claims: the checkable tokens in an answer (amounts and other numbers, dates, last 4 digits,
  merchant and product words). A claim is supported when the same token is in the evidence.
  An answer's score is supported / total claims (None when it makes no checkable claim, e.g. a
  greeting).
- Vectors: every sentence of an answer and every evidence item become term-frequency vectors
  (normalized tokens, no stop words); their cosine similarity is the heatmap the console draws,
  with the tokens they share.

Deterministic, no model and no external service, so it costs nothing and can't hallucinate. It
checks grounding, not correctness: a right number copied from the wrong row still "matches".
Embeddings (e.g. Bedrock Titan) could replace the vectorizer to catch paraphrases.
"""

import json
import math
import re
import unicodedata
from collections import Counter

STOP_WORDS = set(
    """
    a al algo algun alguna algunas alguno algunos ante aqui asi aun cada como con contra cual
    cuando de del desde donde dos el ella ellas ellos en entre era es esa ese eso esta estas
    este esto estos fue ha hay hasta la las le les lo los mas me mi mis muy nada ni no nos o
    otra otro para pero poco por porque puede que quien se sea ser si sin sobre solo su sus
    tambien te tengo tiene tu tus un una uno unos usted ya yo hola gracias puedo ayudar ayudo
    necesitas algo mas cuenta cuentas the and for with you your esta estan
    ao aos as com da das do dos ele ela em essa esse isso esta nao na nas no nos os ou pela
    pelo por que se sem seu sua seus suas tem um uma voce ola obrigado posso ajudar
    """.split()
)
MONTHS = {
    "enero": "01", "janeiro": "01", "febrero": "02", "fevereiro": "02", "marzo": "03",
    "marco": "03", "abril": "04", "mayo": "05", "maio": "05", "junio": "06", "junho": "06",
    "julio": "07", "julho": "07", "agosto": "08", "septiembre": "09", "setembro": "09",
    "octubre": "10", "outubro": "10", "noviembre": "11", "novembro": "11", "diciembre": "12",
    "dezembro": "12",
}  # fmt: skip
NUMBER = re.compile(r"\d[\d.,]*\d|\d")
# The dataset's values are English codes; Nova answers in Spanish or Portuguese. An evidence value
# also counts as its translations, so "Activa" is backed by "Active".
TRANSLATIONS = {
    "active": "activa activo ativa ativo",
    "blocked": "bloqueada bloqueado",
    "closed": "cerrada cerrado encerrada encerrado fechada fechado",
    "suspended": "suspendida suspendido suspensa suspenso",
    "approved": "aprobada aprobado aprovada aprovado",
    "declined": "rechazada rechazado recusada recusado",
    "pending": "pendiente pendente",
    "reversed": "reversada reversado revertida estornada estornado",
    "purchase": "compra",
    "payment": "pago pagamento",
    "withdrawal": "retiro saque",
    "deposit": "deposito",
    "transfer": "transferencia",
    "insufficient_funds": "fondos insuficientes saldo insuficiente",
    "expired_card": "vencida expirada",
    "open": "abierta aberta",
    "process": "proceso tramite andamento",
    "escalated": "escalada escalado",
    "resolved": "resuelta resolvida",
}
MAX_ANSWERS = 12
# A question or exclamation opens with these, anywhere in a sentence ("Hola, ¿Podrías...?"):
# the word right after one is capitalized for that reason, not because it is a name.
OPENERS = "¿¡"


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _number_token(raw: str) -> str:
    """ "4.850.320,75", "4,850,320.75" and "4850320.75" -> "4850320": the integer part, which
    is what answers usually round to."""
    digits = raw.replace(" ", "")
    # A final group of 1-2 digits after the last separator is the decimal part.
    match = re.match(r"^(.*?)[.,](\d{1,2})$", digits)
    if match and re.search(r"\d", match.group(1)):
        digits = match.group(1)
    return re.sub(r"\D", "", digits)


def tokens(text: str) -> list[str]:
    """Normalized tokens: numbers without separators, words without accents or stop words."""
    plain = _plain(text)
    out = [_number_token(m.group()) for m in NUMBER.finditer(plain)]
    for word in re.findall(r"[a-z][a-z-]{2,}", plain):
        if word in MONTHS:
            out.append(MONTHS[word])
        elif word not in STOP_WORDS:
            out.append(word)
    return [t for t in out if t]


def _claims(text: str, ignore: set[str]) -> list[tuple[str, str]]:
    """(token, as written) for the checkable parts of an answer: numbers, and capitalized words
    that don't start a sentence or line (merchant, product and city names). Labels ("Monto:")
    and `ignore` (the customer's name, the bank's) aren't claims."""
    found: list[tuple[str, str]] = []
    for m in NUMBER.finditer(text):
        token = _number_token(m.group())
        if len(token) >= 2:  # single digits ("1 transacción") are too generic
            found.append((token, m.group()))
    clean = re.sub(r"\*\*|__|`", "", text)
    for sentence in _sentences(clean):
        for m in re.finditer(r"\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ]{2,})(\s*:)?", sentence):
            word = _plain(m.group(1))
            # Capitalized because it starts the sentence or follows an opening "¿" or "¡". After a
            # quote or a parenthesis it stays a claim: «Starbucks» is a name to check.
            first = m.start() == 0 or sentence[m.start() - 1] in OPENERS
            if first or m.group(2) or word in STOP_WORDS or word in MONTHS or word in ignore:
                continue
            found.append((word, m.group(1)))
    seen, unique = set(), []
    for token, shown in found:
        if token not in seen:
            seen.add(token)
            unique.append((token, shown))
    return unique


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -*•") for p in parts if len(p.strip(" -*•")) > 3]


def _cosine(a: Counter, b: Counter) -> float:
    dot = sum(a[t] * b[t] for t in a.keys() & b.keys())
    norm = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return dot / norm if norm else 0.0


def _evidence_text(item: dict) -> str:
    """The values in a tool result, as text (keys like "transaction_at" aren't evidence)."""
    try:
        data = json.loads(item.get("result", ""))
    except (TypeError, ValueError):
        return str(item.get("result", ""))
    values: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif node is not None:
            values.append(str(node))

    walk(data)
    text = " ".join(values)
    extra = [
        TRANSLATIONS[w] for w in set(re.findall(r"[a-z_]+", _plain(text))) if w in TRANSLATIONS
    ]
    return " ".join([text, *extra])


IGNORED = {"nova", "novabank"}


def analyze(transcript: list[dict], evidence: list[dict], customer_name: str | None = None) -> dict:
    """Faithfulness of the assistant messages in `transcript` to `evidence` (see module doc).
    `customer_name` isn't a claim: Nova greets the customer, it doesn't read the name from data."""
    ignore = IGNORED | set(tokens(customer_name or ""))
    evidence_vectors = [Counter(tokens(_evidence_text(e))) for e in evidence]
    evidence_tokens = set().union(*evidence_vectors) if evidence_vectors else set()
    answers = []
    for index, message in enumerate(transcript):
        if message.get("role") != "assistant" or not message.get("text", "").strip():
            continue
        text = message["text"]
        claims = [
            {"token": token, "text": shown, "supported": token in evidence_tokens}
            for token, shown in _claims(text, ignore)
        ]
        sentences = []
        for sentence in _sentences(re.sub(r"\*\*|__|`", "", text)):
            vector = Counter(tokens(sentence))
            sentences.append(
                {
                    "text": sentence,
                    "similarity": [round(_cosine(vector, ev), 3) for ev in evidence_vectors],
                    "shared": [sorted(vector.keys() & ev.keys())[:8] for ev in evidence_vectors],
                }
            )
        supported = sum(c["supported"] for c in claims)
        answers.append(
            {
                "index": index,
                "text": text,
                "claims": claims,
                "score": round(supported / len(claims), 3) if claims else None,
                "sentences": sentences,
            }
        )
    answers = answers[-MAX_ANSWERS:]
    scored = [a for a in answers if a["score"] is not None]
    total_claims = sum(len(a["claims"]) for a in scored)
    return {
        "evidence": [
            {"tool": e.get("tool"), "args": e.get("args", {}), "at": e.get("at")} for e in evidence
        ],
        "answers": answers,
        # Over all claims, so a long grounded answer weighs more than a one-number reply.
        "overall": round(sum(c["supported"] for a in scored for c in a["claims"]) / total_claims, 3)
        if total_claims
        else None,
    }


def for_case(case: dict) -> dict:
    """`analyze` for a handed-over case: its transcript against the evidence its tools returned."""
    name = (case.get("verified_facts") or {}).get("first_name")
    return analyze(case.get("transcript", []), case.get("evidence", []), name)
