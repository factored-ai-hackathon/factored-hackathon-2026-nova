"""Builds the knowledge index: reads the documents, adds the branch chunks generated from the public
assistant's data, embeds every chunk with Amazon Titan Text Embeddings V2 and writes
backend/app/agent/knowledge/index.json (the file the Lambda ships).

From backend/ (Bedrock; a few dozen short texts, a fraction of a cent):
    AWS_PROFILE=hackathon PYTHONPATH=. uv run python ../ml/rag/build_index.py
    ... --no-embed    # chunks only, no vectors (lexical search still works)
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.agent import public_info  # noqa: E402
from app.agent.knowledge import INDEX_PATH, KNOWLEDGE_DIR, Chunk, TitanEmbedder  # noqa: E402
from app.config import get_settings  # noqa: E402

MODEL_ID = "amazon.titan-embed-text-v2:0"
DIMENSIONS = 512

BRANCH_TITLE = {
    "es": "Sucursales y horarios en {country}",
    "pt": "Agências e horários em {country}",
}
BRANCH_INTRO = {
    "es": "NovaBank tiene estas sucursales en {country}: ",
    "pt": "O NovaBank tem estas agências em {country}: ",
}
BRANCH_SOURCE = {
    "es": "equipo (ficticio); sucursales inventadas",
    "pt": "equipe (fictício); agências inventadas",
}


def branch_chunks(lang: str) -> list[Chunk]:
    chunks = []
    for country, info in public_info.PUBLIC_INFO.items():
        shown = public_info.COUNTRY_NAMES_PT[country] if lang == "pt" else country
        parts = [
            f"{b.name} ({b.city}), {b.address}: {public_info.format_hours(b.hours, lang)}."
            for b in info.branches
        ]
        chunks.append(
            Chunk(
                id=f"branches-{country.lower().replace('é', 'e')}",
                lang=lang,
                title=BRANCH_TITLE[lang].format(country=shown),
                text=BRANCH_INTRO[lang].format(country=shown) + " ".join(parts),
                source=BRANCH_SOURCE[lang],
            )
        )
    return chunks


def load_chunks() -> list[Chunk]:
    chunks = []
    for lang in ("es", "pt"):
        docs = yaml.safe_load((KNOWLEDGE_DIR / f"docs_{lang}.yaml").read_text(encoding="utf-8"))
        chunks += [
            Chunk(d["id"], lang, d["title"], " ".join(d["text"].split()), d["source"]) for d in docs
        ]
        chunks += branch_chunks(lang)
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-embed", action="store_true")
    args = parser.parse_args()

    chunks = load_chunks()
    if not args.no_embed:
        embedder = TitanEmbedder(MODEL_ID, get_settings().aws_region, DIMENSIONS)
        for chunk in chunks:
            chunk.vector = [round(x, 5) for x in embedder._embed(chunk.searchable)]
        print(f"embedded {len(chunks)} chunks with {MODEL_ID} ({DIMENSIONS} dimensions)")
    out = {
        "meta": {
            "built": datetime.now(UTC).isoformat(timespec="seconds"),
            "model": None if args.no_embed else MODEL_ID,
            "dimensions": None if args.no_embed else DIMENSIONS,
            "chunks": len(chunks),
            "provenance": "team-written, fictitious NovaBank documents (ES + PT)",
        },
        "chunks": [c.__dict__ for c in chunks],
    }
    INDEX_PATH.write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"wrote {INDEX_PATH} ({INDEX_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
