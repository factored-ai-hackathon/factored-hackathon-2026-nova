"""Intent of the customer's message (decision 29): the learned component.

A TF-IDF + logistic regression classifier trained in ml/intent (scikit-learn), exported to
intent_model.json and run here in plain Python, so the Lambda doesn't need scikit-learn. It maps
the customer's words to the bank's contact reasons (the dataset's reason_category) plus `other`
(greetings, thanks, off-topic), and each reason to the first contact resolution rate the bank
actually had for it (fact_interaction). The graph uses it in code: for the reasons that a first
contact rarely solves (complaints, retention) Nova offers a human sooner, and the case the human
receives says what the classifier saw.

The preprocessing mirrors scikit-learn's TfidfVectorizer (lowercase, strip_accents="unicode",
word and char_wb n-grams, sublinear tf, idf, l2 per vectorizer); a test checks the probabilities
match scikit-learn's on sample texts.
"""

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path

MODEL_PATH = Path(__file__).parent / "intent_model.json"

# Reasons whose first contact resolution is lowest in the bank's data (complaints 43%, retention
# 60%; the next one, commercial, is 65%): for these Nova offers a human early.
EARLY_HANDOFF_INTENTS = ("complaint", "retention")

_WHITE_SPACES = re.compile(r"\s\s+")


def _strip_accents(text: str) -> str:
    """scikit-learn's strip_accents_unicode."""
    try:
        text.encode("ASCII", errors="strict")
        return text
    except UnicodeEncodeError:
        normalized = unicodedata.normalize("NFKD", text)
        return "".join(c for c in normalized if not unicodedata.combining(c))


class _Vectorizer:
    """One fitted TfidfVectorizer (analyzer "word" or "char_wb")."""

    def __init__(self, spec: dict) -> None:
        self.analyzer = spec["analyzer"]
        self.min_n, self.max_n = spec["ngram_range"]
        self.lowercase = spec["lowercase"]
        self.strip_accents = spec["strip_accents"] == "unicode"
        self.sublinear_tf = spec["sublinear_tf"]
        self.token_pattern = re.compile(spec.get("token_pattern") or r"(?u)\b\w\w+\b")
        self.vocabulary: dict[str, int] = spec["vocabulary"]
        self.idf: list[float] = spec["idf"]
        self.offset = 0  # this vectorizer's first column in the concatenated features

    def _preprocess(self, text: str) -> str:
        if self.lowercase:
            text = text.lower()
        return _strip_accents(text) if self.strip_accents else text

    def _ngrams(self, text: str) -> list[str]:
        text = self._preprocess(text)
        if self.analyzer == "word":
            tokens = self.token_pattern.findall(text)
            grams = []
            for n in range(self.min_n, self.max_n + 1):
                grams += [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]
            return grams
        # char_wb: character n-grams inside word boundaries, words padded with a space
        grams = []
        for word in _WHITE_SPACES.sub(" ", text).split():
            word = f" {word} "
            for n in range(self.min_n, self.max_n + 1):
                offset = 0
                grams.append(word[offset : offset + n])
                while offset + n < len(word):
                    offset += 1
                    grams.append(word[offset : offset + n])
                if offset == 0:  # a word shorter than n counts once
                    break
        return grams

    def transform(self, text: str) -> dict[int, float]:
        counts = Counter(g for g in self._ngrams(text) if g in self.vocabulary)
        row = {}
        for gram, count in counts.items():
            tf = 1 + math.log(count) if self.sublinear_tf else count
            index = self.vocabulary[gram]
            row[self.offset + index] = tf * self.idf[index]
        norm = math.sqrt(sum(v * v for v in row.values()))
        return {k: v / norm for k, v in row.items()} if norm else row


@dataclass(frozen=True)
class Intent:
    label: str  # transactional | product | complaint | technical | commercial | retention | other
    confidence: float  # the classifier's probability for `label`
    reason_category: str | None  # the dataset's name for it (None for "other")
    fcr_rate: float | None  # first contact resolution the bank had for this reason
    confident: bool  # confidence >= the model's threshold

    @property
    def early_handoff(self) -> bool:
        return self.confident and self.label in EARLY_HANDOFF_INTENTS

    def as_dict(self) -> dict:
        return asdict(self) | {"early_handoff": self.early_handoff}


class IntentModel:
    def __init__(self, spec: dict) -> None:
        self.classes: list[str] = spec["classes"]
        self.vectorizers = [_Vectorizer(v) for v in spec["vectorizers"]]
        offset = 0
        for vectorizer in self.vectorizers:
            vectorizer.offset = offset
            offset += len(vectorizer.idf)
        self.coef: list[list[float]] = spec["coef"]
        self.intercept: list[float] = spec["intercept"]
        self.threshold: float = spec["threshold"]
        self.rates: dict[str, dict] = spec["resolution_rates"]
        self.version: str = spec.get("version", "")

    def predict_proba(self, text: str) -> dict[str, float]:
        features: dict[int, float] = {}
        for vectorizer in self.vectorizers:
            features.update(vectorizer.transform(text))
        logits = [
            b + sum(w[i] * x for i, x in features.items())
            for w, b in zip(self.coef, self.intercept, strict=True)
        ]
        top = max(logits)
        exps = [math.exp(z - top) for z in logits]
        total = sum(exps)
        return {c: e / total for c, e in zip(self.classes, exps, strict=True)}

    def classify(self, text: str) -> Intent:
        probs = self.predict_proba(text)
        label = max(probs, key=probs.__getitem__)
        rate = self.rates.get(label) or {}
        return Intent(
            label=label,
            confidence=round(probs[label], 4),
            reason_category=rate.get("reason_category"),
            fcr_rate=rate.get("fcr_rate"),
            confident=probs[label] >= self.threshold,
        )


@cache
def get_intent_model() -> IntentModel:
    return IntentModel(json.loads(MODEL_PATH.read_text(encoding="utf-8")))


def classify(text: str) -> Intent:
    return get_intent_model().classify(text)


def update(previous: dict | None, intent: Intent) -> dict | None:
    """The conversation's intent: the latest confident one that isn't small talk. A "gracias" or
    a low-confidence message keeps what the conversation was about."""
    if intent.confident and intent.label != "other":
        return intent.as_dict()
    return previous


# --- the hint for the model (fixed text, not the model's) ---------------------------------------

HINTS = {
    "es": {
        "complaint": "Un clasificador en código ve este mensaje como una queja (confianza "
        "{confidence:.0%}). En este banco solo el {fcr:.0%} de las quejas se resuelve en el primer "
        "contacto. En esta misma respuesta, reconoce el problema y ofrece comunicarlo con un "
        "asesor humano que puede atender la queja formalmente; no lo hagas esperar con varias "
        "preguntas. "
        "Si prefiere seguir contigo, ayuda con lo que puedas verificar con tus herramientas.",
        "retention": "Un clasificador en código ve este mensaje como una intención de cancelar o "
        "dejar el banco (confianza {confidence:.0%}; en este banco solo el {fcr:.0%} de estos "
        "contactos se resuelve en el primero). No puedes cancelar ni cerrar productos: dilo con "
        "claridad, pregunta brevemente el motivo si no lo dijo y ofrece comunicarlo con un asesor.",
    },
    "pt": {
        "complaint": "Um classificador em código vê esta mensagem como uma reclamação (confiança "
        "{confidence:.0%}). Neste banco só {fcr:.0%} das reclamações são resolvidas no primeiro "
        "contato. Nesta mesma resposta, reconheça o problema e ofereça transferir para um "
        "atendente humano que pode registrar a reclamação formalmente; não o faça esperar com "
        "várias perguntas. Se preferir continuar com você, ajude com o que puder verificar com "
        "suas ferramentas.",
        "retention": "Um classificador em código vê esta mensagem como intenção de cancelar ou "
        "sair do banco (confiança {confidence:.0%}; neste banco só {fcr:.0%} desses contatos são "
        "resolvidos no primeiro). Você não pode cancelar nem encerrar produtos: diga isso com "
        "clareza, pergunte brevemente o motivo se não foi dito e ofereça um atendente humano.",
    },
}


def hint(intent: Intent, lang: str) -> str | None:
    """Extra system prompt line for this turn, only for the early-handoff intents."""
    if not intent.early_handoff:
        return None
    template = HINTS.get(lang, HINTS["es"])[intent.label]
    return template.format(confidence=intent.confidence, fcr=intent.fcr_rate or 0)
