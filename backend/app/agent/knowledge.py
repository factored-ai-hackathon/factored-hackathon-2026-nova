"""Knowledge search for Nova: answers about products, policies and how things work (decision 32).

The model calls `search_policies(query)` and answers ONLY from what comes back, citing the title;
when nothing relevant comes back it says so and offers a person. The knowledge is a small fixed
set of team-written, fictitious documents (app/agent/knowledge/docs_es.yaml, docs_pt.yaml), one
chunk per idea (~60-120 tokens), in Spanish and Portuguese.

Retrieval is hybrid and cheap (no vector database, nothing to run):
- lexical: BM25 over accent-free words cut to 6 letters (a crude stemmer: transferencia and
  transferencias meet), computed at load;
- dense: Amazon Titan Text Embeddings V2 (512 dimensions). The chunks' vectors are computed once
  by ml/rag/build_index.py and shipped in index.json; only the question is embedded per search.
  If the embedding call fails (no permission, timeout) the search silently falls back to lexical.
- the two rankings are fused with reciprocal rank fusion. When neither signal is confident enough
  the search abstains (returns nothing) instead of returning the least bad chunk: the thresholds
  are chosen on a dev split of held-out questions (ml/rag/evaluate.py), not by hand.
Search is restricted to the conversation's language.
"""

import asyncio
import json
import logging
import math
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
INDEX_PATH = KNOWLEDGE_DIR / "index.json"
THRESHOLDS_PATH = KNOWLEDGE_DIR / "thresholds.json"
SEARCH_TOOL_NAME = "search_policies"
TOP_K = 3
MAX_QUERY_CHARS = 300
RRF_K = 60  # reciprocal rank fusion constant
STEM_LENGTH = 6
BM25_K1, BM25_B = 1.5, 0.75
DENSE_COOLDOWN_SECONDS = 300  # after an embedding failure, stay lexical for a while

STOPWORDS = set(
    """a al algo ante con como cual cuales cuando cuanto cuantos de del desde donde el ella ellos en
    entre era es esta estan este esto fue ha hay la las le les lo los mas me mi mis muy ni no nos o
    para pero por porque que quien se si sin sobre su sus te tengo tiene tu tus un una uno y ya yo
    voy puedo puede pueden hago hace hacer
    ao aos as ate com como cada qual quais quando quanto quantos da das de dela deles do dos e ela
    em entre era essa esse esta este eu foi ha isso la mais mas me meu minha muito na nas nao nem no
    nos o os ou para pela pelo por que quem se sem seu sua te tem tenho um uma voce vou posso pode
    podem faco faz fazer""".split()
)


def plain(text: str) -> str:
    """Lowercase without accents."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def tokens(text: str, stems: bool = True) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9]+", plain(text)) if len(w) > 1 and w not in STOPWORDS]
    return [w[:STEM_LENGTH] for w in words] if stems else words


@dataclass
class Chunk:
    id: str  # the topic: the same in Spanish and Portuguese
    lang: str
    title: str
    text: str
    source: str
    vector: list[float] | None = None

    @property
    def searchable(self) -> str:
        return f"{self.title}. {self.text}"


@dataclass
class Thresholds:
    """Below these the search abstains. Calibrated on the dev questions (ml/rag/evaluate.py)."""

    dense: float = 0.0  # top cosine similarity (hybrid mode)
    lexical: float = 0.0  # top share of the query's idf mass matched (hybrid mode)
    lexical_only: float = 0.0  # the same, when there is no dense signal


@dataclass
class Hit:
    chunk: Chunk
    score: float  # fused rank score
    dense: float | None
    lexical: float  # share of the query's idf mass matched, 0..1


@dataclass
class SearchResult:
    hits: list[Hit]
    abstained: bool
    mode: str  # "hybrid" | "lexical"
    top_dense: float | None = None
    top_lexical: float = 0.0


class Embedder(Protocol):
    async def embed_query(self, text: str) -> list[float]: ...


class _Bm25:
    """BM25 over one language's chunks. `confidence` is the best score as a share of the highest
    score any chunk could get for the query (every query term matched): comparable between
    queries, which a raw BM25 score is not."""

    def __init__(self, texts: list[str], stems: bool):
        self.stems = stems
        self.docs = [Counter(tokens(t, stems)) for t in texts]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = (sum(self.lengths) / len(self.lengths)) if self.lengths else 1.0
        df: Counter = Counter()
        for doc in self.docs:
            df.update(doc.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str) -> tuple[list[float], float]:
        terms = set(tokens(query, self.stems))
        ceiling = sum(self.idf.get(t, 0.0) * (BM25_K1 + 1) for t in terms)
        out = []
        for doc, length in zip(self.docs, self.lengths, strict=True):
            score = 0.0
            for term in terms:
                tf = doc.get(term, 0)
                if not tf:
                    continue
                norm = tf + BM25_K1 * (1 - BM25_B + BM25_B * length / self.avg)
                score += self.idf[term] * tf * (BM25_K1 + 1) / norm
            out.append(score)
        return out, ceiling


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _ranks(scores: list[float]) -> list[int]:
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    ranks = [0] * len(scores)
    for rank, i in enumerate(order):
        ranks[i] = rank
    return ranks


class KnowledgeBase:
    def __init__(
        self,
        chunks: list[Chunk],
        thresholds: Thresholds | None = None,
        embedder: Embedder | None = None,
        embed_timeout: float = 3.0,
    ):
        self.thresholds = thresholds or Thresholds()
        self.embedder = embedder
        self.embed_timeout = embed_timeout
        self._dense_failed_at: float | None = None
        self.by_lang: dict[str, list[Chunk]] = {}
        for chunk in chunks:
            self.by_lang.setdefault(chunk.lang, []).append(chunk)
        self._bm25 = {
            lang: _Bm25([c.searchable for c in group], stems=True)
            for lang, group in self.by_lang.items()
        }

    def _dense_available(self) -> bool:
        if self.embedder is None:
            return False
        failed = self._dense_failed_at
        return failed is None or time.monotonic() - failed > DENSE_COOLDOWN_SECONDS

    async def _query_vector(self, query: str) -> list[float] | None:
        if not self._dense_available():
            return None
        try:
            return await asyncio.wait_for(self.embedder.embed_query(query), self.embed_timeout)  # type: ignore[union-attr]
        except Exception as exc:  # no permission, throttling, timeout: lexical only for a while
            self._dense_failed_at = time.monotonic()
            logger.warning("embedding failed, searching lexically: %s", exc)
            return None

    def rank(
        self, query: str, lang: str, query_vector: list[float] | None, k: int = TOP_K
    ) -> SearchResult:
        """The search with the query's vector already known (the evaluation passes cached ones)."""
        chunks = self.by_lang.get(lang, [])
        if not chunks or not tokens(query):
            return SearchResult([], True, "lexical")
        raw, ceiling = self._bm25[lang].scores(query)
        lexical = [s / ceiling if ceiling else 0.0 for s in raw]
        dense = None
        if query_vector is not None:
            dense = [_cosine(query_vector, c.vector) if c.vector else 0.0 for c in chunks]
        # Fuse only the signals that say something: when no word of the question is in any
        # chunk, the lexical order is arbitrary and would only add noise.
        signals = [lexical] if max(lexical) > 0 else []
        if dense is not None:
            signals.append(dense)
        if len(signals) == 1:
            fused = signals[0]
        else:
            ranked = [_ranks(signal) for signal in signals]
            fused = [sum(1 / (RRF_K + r[i]) for r in ranked) for i in range(len(chunks))]
        order = sorted(range(len(chunks)), key=lambda i: fused[i], reverse=True)[:k]
        hits = [Hit(chunks[i], fused[i], dense[i] if dense else None, lexical[i]) for i in order]
        top_lex = max(lexical)
        top_dense = max(dense) if dense else None
        if dense is None:
            abstain = top_lex < self.thresholds.lexical_only
        else:
            abstain = top_dense < self.thresholds.dense and top_lex < self.thresholds.lexical
        return SearchResult(
            [] if abstain else hits,
            abstain,
            "lexical" if dense is None else "hybrid",
            top_dense,
            top_lex,
        )

    async def search(self, query: str, lang: str, k: int = TOP_K) -> SearchResult:
        vector = await self._query_vector(query)
        return self.rank(query, lang, vector, k)


# --- loading and the tool the model calls -----------------------------------------------------


class TitanEmbedder:
    """Amazon Titan Text Embeddings V2 on Bedrock (normalized vectors)."""

    def __init__(self, model_id: str, region: str, dimensions: int = 512):
        import boto3

        self.client = boto3.client("bedrock-runtime", region_name=region)
        self.model_id, self.dimensions = model_id, dimensions

    def _embed(self, text: str) -> list[float]:
        body = json.dumps({"inputText": text, "dimensions": self.dimensions, "normalize": True})
        response = self.client.invoke_model(modelId=self.model_id, body=body)
        return json.loads(response["body"].read())["embedding"]

    async def embed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._embed, text)


def load_chunks(path: Path = INDEX_PATH) -> tuple[list[Chunk], dict[str, Any]]:
    if not path.exists():
        return [], {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Chunk(**c) for c in data["chunks"]], data.get("meta", {})


def load_thresholds(path: Path = THRESHOLDS_PATH) -> Thresholds:
    if not path.exists():
        return Thresholds()
    data = json.loads(path.read_text(encoding="utf-8"))["thresholds"]
    return Thresholds(**data)


def build_knowledge_base(settings: Any) -> KnowledgeBase:
    chunks, meta = load_chunks()
    if not chunks:
        logger.warning("no knowledge index at %s: search_policies will find nothing", INDEX_PATH)
    embedder = None
    if settings.llm_provider != "fake" and settings.knowledge_dense and meta.get("model"):
        embedder = TitanEmbedder(meta["model"], settings.aws_region, meta.get("dimensions", 512))
    return KnowledgeBase(chunks, load_thresholds(), embedder)


@lru_cache
def get_knowledge_base() -> KnowledgeBase:
    from app.config import get_settings

    return build_knowledge_base(get_settings())


@tool
def search_policies(query: str) -> str:
    """Search NovaBank's documents about products, policies and how things work: why a purchase is
    declined, product statuses, lost cards, transfer times and limits, complaints and their
    deadlines, credit card basics, late payments, security, login, identity verification,
    documents, currencies, channels, human advisors, data freshness, opening an account, privacy,
    what Nova cannot do, branches and opening hours. Use it for general questions (not for the
    customer's own data) and answer ONLY from what it returns, naming the document title. If it
    returns nothing relevant, say you don't have that information and offer a human advisor."""
    return ""


async def run_search(args: dict, lang: str, kb: KnowledgeBase | None = None) -> str:
    query = str(args.get("query") or "").strip()[:MAX_QUERY_CHARS]
    kb = kb or get_knowledge_base()
    result = await kb.search(query, lang)
    if result.abstained or not result.hits:
        return json.dumps(
            {
                "results": [],
                "note": "No relevant document. Do not answer from memory: say you don't have "
                "that information and offer a human advisor.",
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "results": [
                {"title": h.chunk.title, "text": h.chunk.text, "source": h.chunk.source}
                for h in result.hits
            ]
        },
        ensure_ascii=False,
    )


__all__ = [
    "SEARCH_TOOL_NAME",
    "Chunk",
    "KnowledgeBase",
    "SearchResult",
    "Thresholds",
    "get_knowledge_base",
    "run_search",
    "search_policies",
    "tokens",
]
