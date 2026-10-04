# Nova: first-contact resolution for a bank's contact center

**Nova resolves declined-payment and complaint questions on the first contact, with the customer's
own data, and when it can't, hands the case to a person with the verified facts, the evidence and a
faithfulness check, so the customer repeats nothing.**

Factored AI & Data Hackathon 2026 · AI-first banking agent · Spanish and Portuguese.

Team: **Nova** · Repository: `factored-hackathon-2026-nova`.

| | |
|---|---|
| **Live demo** | [https://d2k8cgrqduyk2o.cloudfront.net](https://d2k8cgrqduyk2o.cloudfront.net): the demo page, with the three parts below |
| Customer app | [`/login`](https://d2k8cgrqduyk2o.cloudfront.net/login): open **"Modo demo: clientes de prueba"** on the login page; password `Nova2026`, the SMS code is shown on screen |
| Human agent console | [`/console`](https://d2k8cgrqduyk2o.cloudfront.net/console), key `Asesor2026` (shown in the field) |
| How the models are measured | [`/models`](https://d2k8cgrqduyk2o.cloudfront.net/models), password `Modelos2026` (shown in the field); it also shows live production numbers and how the demo is protected, with what the firewall blocked in the last 24 h |
| Full demo guide | [docs/demo.md](docs/demo.md) |

All customers are the challenge's **synthetic** dataset; no real person's data is used anywhere.

## The problem, in the bank's own data

In the LATAM Bank dataset (686k contact-center interactions), the reason for contact is the one thing
that moves first contact resolution (FCR). Channel, agent experience and sentiment do not:

| Reason | Interactions | Resolved on the first contact |
|---|---|---|
| Transactional | 240,056 | 90.6% |
| Product | 150,863 | 89.1% |
| Technical | 102,899 | 69.6% |
| Commercial | 54,879 | 65.0% |
| Retention | 20,578 | 60.0% |
| **Complaint** | 117,021 | **43.4%** |

The analysis behind it, including what did *not* move FCR, is in [docs/data-findings.md](docs/data-findings.md).

**Who has it:** the customer who writes in about a declined payment, a charge they don't recognize or
a complaint, and the human agent who receives the case and has to start over.

## What Nova does (3-minute demo path)

1. **Log in** as the demo customer *"Pago rechazado"* (a payment declined in the last month).
2. Ask *"¿Por qué me rechazaron una compra?"*. Nova reads **that customer's** transactions and
   answers with the merchant, the amount and the reason from the data (e.g. code 51, insufficient
   funds). No verification again: the login already proved who they are.
3. Say *"No reconozco este cargo"*. Fraud and disputes go to a person at once: Nova opens a case and
   tells the customer its number.
4. Open **`/console`**. The case shows Nova's summary and open questions, the **facts the system
   verified** (from the session, not from the model's words), the **account data Nova actually
   read**, and how **faithful** each answer was to that data. The agent replies in the same chat.
5. Switch the chat to Portuguese (*"Qual é o saldo das minhas contas?"*): same agent, same rules.

## What is different

**Core**
- **Permissions in code, not in the prompt.** Account tools take no customer id: the backend uses the
  verified session's. Identity verification (login with SMS code, or document + date of birth + code
  in the chat) runs outside the model. Every tool call goes to an audit trail.
- **A handoff built by code.** The case for the person carries verified facts and the evidence of the
  tools that ran, so the model cannot invent them.
- **Faithfulness in the agent console.** Each amount, date or name in Nova's answers is marked as found
  (or not) in the data it consulted.
- **An evaluation that shows the bad first run.** See [Evidence](#evidence).

**Supporting**
- An **intent classifier** (TF-IDF + logistic regression, 0.3 ms, $0) flags complaints and retention
  requests, the reasons the bank rarely solves on the first contact, so Nova offers a person sooner.
- **Knowledge search** (hybrid BM25 + Titan embeddings) for policy questions, citing its source.
- A **public assistant** outside the login (branches and hours), sessions that survive a reload, and
  an incremental **data pipeline** (dbt on Athena) with a freshness policy.

## Evidence

Every number below is generated from files in this repo, never typed by hand.

| What | Result | Where |
|---|---|---|
| Held-out evaluation, first run (60 cases × 3, before any fix) | safe automated resolution **91.1%**, 0 unsafe outcomes in 180 runs | [evals/report/REPORT.md](evals/report/REPORT.md) |
| 13 repeated passes (before the decision 38 fix, see the report) | safe automated resolution **99.9%** (sd 0.3), **0 unsafe outcomes in 2,340 runs**, p50 1.6 s / p95 2.9 s | same |
| End to end against the live app (before Deploy #64, see the report) | **31/32** answers right and safe, first token 0.9 s | same |
| Intent classifier vs keyword rules | macro-F1 **0.853** vs 0.618 (Claude zero-shot: 0.890, but 0.57 s and $0.25 per 1,000) | [ml/README.md](ml/README.md), `/models` |
| Does the classifier change behavior? (ablation in the real agent) | complaint and retention messages where a person was offered or a case opened: **95%** with it vs **73%** without | same |
| Knowledge search | recall@1 **87%**, recall@3 **97%**, MRR 0.93 (BM25 alone: 82%, 0.88) | [ml/rag/README.md](ml/rag/README.md), `/models` |
| Cost | **$0.0041 per conversation** (Claude Haiku 4.5 on Bedrock), 84% of it input tokens | `/models` |

The first run is the honest estimate: the later runs reuse the same cases after fixing what the first
one found (the report lists every finding and fix).

## Architecture

```mermaid
flowchart LR
  U[Customer<br/>ES / PT] --> CF[CloudFront + S3<br/>React app]
  H[Human agent<br/>/console] --> CF
  CF --> L[Lambda function URL<br/>FastAPI, streaming]
  L --> G[LangGraph agent<br/>identity, tools, handoff in code]
  G --> B[Amazon Bedrock<br/>Claude Haiku 4.5, Titan embeddings]
  G --> D[(DynamoDB<br/>customers, sessions,<br/>interactions, cases)]
  S3[(S3 data lake<br/>raw CSV → Parquet)] --> A[Athena + dbt] --> D
```

Serverless and scale-to-zero on purpose: the team pays for it. Production calls models only through
Bedrock; the public API is rate-limited per visitor. Infrastructure is Terraform
([infra/](infra/)); details in [docs/architecture.md](docs/architecture.md), every decision with its
reason in [docs/decisions.md](docs/decisions.md).

## How we work on GitHub

- Feature branches → pull request into `development`, with CI (backend, frontend and agent evals).
- Releases: a pull request `development` → `main`, merged with a merge commit; a check blocks any other
  branch into `main`. The release is **manual on purpose** (the release owner reviews what goes live),
  then deploy and a dated release tag (`vYYYY.MM.DD`) are automatic.
- Decisions are logged in [docs/decisions.md](docs/decisions.md); the team guide is in
  [CONTRIBUTING.md](CONTRIBUTING.md).

## Limitations

- **All data is synthetic.** Evaluation cases, classifier phrases and knowledge questions were written
  by the team (with Claude's help), after building the agent: they show it generalizes across styles we
  wrote, not to real traffic.
- The in-process report uses **two fixture customers**; the end-to-end passes use dataset customers, but
  on a small sample (the public API allows 30 messages per hour per visitor).
- **Portuguese**: the dataset has no Brazilian customers, so Portuguese is covered by the conversation
  and the phrases, not by Brazilian accounts.
- The bank's transcripts carry **no signal to train on** (42 distinct texts in 171k), so the classifier
  learns from team-written phrases and takes the FCR rates from the dataset.
- Abstention is the weak part of the knowledge search; the model reading the chunks does most of it.
- NovaBank's policies and figures are fictitious.
- **Known security limits** (this is a public demo with a synthetic dataset, so we accepted these on purpose; the review is in [docs/decisions.md](docs/decisions.md), decisions 43 and 49):
  - The demo password, the agent console key and the model page password are **published** in this README so judges can get in. They are demo props, not security.
  - The **$5/day model budget is global**: a determined visitor can use it up, and then every visitor gets `429 daily_budget_exhausted` until 00:00 UTC. The per-visitor limit (30 messages per hour) counts an IPv6 visitor by its /64, but it is still a cost cap, not a guarantee of availability.
  - **AWS WAF** on CloudFront refuses at the edge, before the API runs ([infra/app/waf.tf](infra/app/waf.tf)): any API request whose method and path are not one of the routes the app calls (`404 blocked_route`: scanners, other methods, encoded or traversal paths), bodies over 16 KB (`413`), AWS managed rules for known attack patterns and for IPs with a bad reputation (`403`; the reputation list also blocks some VPN and Tor exits), and per-IP rate limits (`429 rate_limited`): 60 per 5 minutes on the live metrics and on login, 120 on the demo panel lookups, 100 on the rest of the API (the polled console and handoff paths left out), 600 on any API path and 3,000 on any path. These are per IP, so many addresses together (a botnet) can still use up the daily model budget above; the app limits cap the cost, not availability.
  - The Lambda **function URL can still be called directly**, bypassing WAF; it answers 403 without the secret header CloudFront adds, but it is still invoked. WAF also counts each IPv6 address separately, so rotating addresses inside a /64 dodges the WAF rule (the app limit still caps the model spend).
  - There is no Content-Security-Policy yet (HSTS, X-Frame-Options, X-Content-Type-Options and Referrer-Policy are set).

## Run it locally

See [docs/setup.md](docs/setup.md). In short: `uv sync`, then from `backend/`
`uv run uvicorn app.main:app --reload --reload-dir app`, and from `frontend/` `npm install && npm run dev`,
then open http://localhost:5173. Tests: `uv run pytest` (backend), `npm test` (frontend).

## Team

| | Role |
|---|---|
| [Paul Montero](https://github.com/lpaulmp) | Backend, platform, agent AI |
| [Esteban Quintero Gómez](https://github.com/Estebanquingo) | Architecture, backend, frontend (the MVP chat foundation and its plan) |
| [Miguel Higorre](https://github.com/miguel-higorre-ch) | Coordination, QA and evaluation, frontend |
| Iris | Initial Kickoff data and ML |

## Contributions

What each person did, from the repository history and the [decisions log](docs/decisions.md). Much of the code was written with Claude Code (an AI coding assistant). Since Oct 2 every pull request also gets a review comment from a review agent (PulMAgent), and every merge and every release is done by a person.

- **Paul Montero**: the agent and its backend (identity verification, account tools, handoff to a human agent and the agent console, intent classifier, knowledge search), the evaluation report, the data pipeline, the infrastructure and the release process.
- **Miguel Higorre**: the banking UI draft (#3), the evaluation issue template and workflow, an evaluation plan (#31), the 14 manual test cases (issues #32 to #45), the report that led to the demo-pool fix (#88, #90) and the fixes to the chat's full view (#85, #89).
- **Esteban Quintero Gómez**: the first version of the chat (Sep 27), with the streaming API, the agent, the React UI and the first evaluations, and the plan for the first end-to-end chat ([docs/plans/mvp-chat.md](docs/plans/mvp-chat.md)).
