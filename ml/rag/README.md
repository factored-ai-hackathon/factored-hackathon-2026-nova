# rag

Knowledge search for Nova (decision 32): answers about products, policies and how things work come
from documents, not from the model's memory. Runtime code: `backend/app/agent/knowledge.py`.

## What it is
- **Documents**: 18 topics in Spanish and Portuguese (`backend/app/agent/knowledge/docs_es.yaml`,
  `docs_pt.yaml`) plus 3 branch-and-hours chunks per language generated from the public assistant's
  data: **42 chunks** of about 60-120 tokens, one idea each (a FAQ-style entry; no overlap needed).
  **Team-written and fictitious**: policies and figures are invented for this demo (each entry says
  so in `source`); the response codes, product statuses, transaction types, channels and document
  types come from the dataset.
- **Retrieval**: hybrid, no vector database. BM25 over accent-free words cut to 6 letters, plus
  Amazon Titan Text Embeddings V2 (512 dimensions) cosine similarity, fused with reciprocal rank
  fusion. The chunks' vectors are computed once (`build_index.py`) and shipped as JSON (196 KB);
  only the question is embedded per search (a fraction of a cent). If the embedding call fails the
  search is lexical only. Searches are restricted to the conversation's language.
- **Use**: the model calls `search_policies(query)`, verified or not (the documents are not
  customer data), answers only from the result, and ends with `Fuente: <document title>`. When the
  result is empty or does not answer, it says so and offers a person.
- **Cost**: one Titan call per policy question. Titan V2 costs $0.02 per million tokens, so a
  question is about $0.000001; the index build was under a cent.

## How it was evaluated (`questions.yaml`, `evaluate.py`, `RESULTS.md`)
98 team-written, synthetic questions (49 ES, 49 PT) written after the documents, in colloquial
phrasing: 76 have a gold document, 20 have none (the right behavior is to find nothing). Half are
**dev** (they only choose the abstention thresholds), half **test** (the reported numbers).

Ranking, answerable test questions (n=38): see `RESULTS.md` for every table, by language and with
the counts. Headline:

| Retriever | Recall@1 | Recall@3 | MRR |
|---|---|---|---|
| BM25 words (baseline) | 82% | 92% | 0.877 |
| BM25 stems | 82% | 84% | 0.864 |
| Titan embeddings only | 82% | 97% | 0.890 |
| **Hybrid (shipped)** | **87%** | **97%** | **0.928** |

The hybrid is better than either signal alone, but the margin is two questions out of 38 for
recall@1: the intervals overlap, so treat it as "at least as good, usually better" rather than a
proven gap. Portuguese gains the most (recall@1 79% → 90%).

**Abstention is the weak part, and that is documented rather than hidden.** Similarity scores do
not separate a question the documents cannot answer from one that is merely hard ("do you have a
branch in Chile?" is close to the branch documents). The thresholds are therefore conservative on
purpose: chosen on the dev split to never drop an answerable question, they drop 1 of 38
answerable test questions and catch 2 of 10 unanswerable ones at the search stage. The rest is left
to the model reading the chunks, measured end to end in `evals/agent/knowledge.yaml`: on 16 live
cases (answerable with figures and a cited source; unanswerable that must say "I don't have it"),
14 pass. The two that do not are questions about data freshness: the model answers from the
session's own "data as of" line instead of searching, which is true but omits the 24-hour policy.

## Limits
- Written by the team, with the same people who wrote the documents: the questions are held out
  from the thresholds, not independent of the authors.
- 42 chunks: it shows the method works and how to evaluate it, not how it scales. At thousands of
  chunks the in-memory cosine would move to a vector store.
- The documents are fictitious: Nova does not know NovaBank's real conditions, because there are none.

## Reproduce
```bash
cd backend
AWS_PROFILE=hackathon PYTHONPATH=. uv run python ../ml/rag/build_index.py   # after editing a document
AWS_PROFILE=hackathon PYTHONPATH=. uv run python ../ml/rag/evaluate.py      # RESULTS.md, thresholds.json
EVAL_LIVE=1 LLM_PROVIDER=bedrock AWS_PROFILE=hackathon uv run pytest -k knowledge_case
```
A test fails if a document changes without rebuilding the index.
