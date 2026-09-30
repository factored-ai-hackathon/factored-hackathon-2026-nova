# ml

Contact center models. Owner: Iris. Large artifacts go to `s3://fh26-hackaton-data/models/`, not to git; the intent model below is the exception (1.4 MB of JSON the Lambda needs, derived only from team-written text).

## Intent classifier (decision 29): model card

**What it does.** Reads each customer message in the chat and returns one of the bank's contact reasons (the dataset's `reason_category`: transactional, product, complaint, technical, commercial, retention) or `other` (greetings, thanks, off-topic), with a probability. Each reason carries the **first contact resolution rate the bank actually had for it** (`fact_interaction`, 686k interactions):

| Intent | `reason_category` | Interactions | FCR |
|---|---|---|---|
| transactional | Transaccional | 240,056 | 90.6% |
| product | Producto | 150,863 | 89.1% |
| technical | Técnico | 102,899 | 69.6% |
| commercial | Comercial | 54,879 | 65.0% |
| retention | Retención | 20,578 | 60.0% |
| complaint | Queja | 117,021 | **43.4%** |

**How the agent uses it** (in code, `backend/app/agent/intent.py` + `graph.py`): when a message is confidently a complaint or retention (the two reasons a first contact rarely solves), that turn's prompt tells Nova the rate and to offer a human sooner (retention: Nova can't close products, so it says so and offers an agent). The conversation's intent goes into the handoff case and the agent console ("Intent (ML model)", confidence, the bank's FCR for it), and every turn's log records label and confidence. It doesn't block anything: security stays in the identity and tool code.

### Why not train on the bank's transcripts
That was the plan. The data doesn't allow it (checked Sep 30 on `latam_raw` / `latam_curated`):

| Target tried | Finding |
|---|---|
| `reason_category` from `call_transcripts.customer_text` | Only **42 distinct texts** in 171,321 transcripts (two "check my balance" openings plus closing phrases). Each one appears in all 6 categories in the same proportions (~35% purity = the majority class). No signal |
| `was_resolved` from the transcript | 76-77% for every text variant. No signal |
| `is_fraud` on transactions | 0.1% positives; flat by amount decile, channel, hour, merchant category, type. `fraud_score` > 40 is always fraud and below 30 almost never: a rule, nothing to learn |
| Complaints: `sla_breached`, `resolution_days` | ~20% and ~15.6 days for every priority, category and case type |
| `was_resolved` from the customer's history | 76-77% regardless of previous contacts or the previous outcome |

The one real pattern in the data is **reason → resolution rate**, so the model learns the part the dataset can't give (reason from free text) and the dataset gives the rate. The transcripts' `detected_intents` / `main_topics` are organizer labels (`consulta_general` for all) and were never used.

### Data
Team-generated, written for this project with Claude Code (not bank customers): **560 training phrases** (40 per class per language, ES + PT) and a **held-out test set of 210** (15 per class per language) written separately in a different style: informal, typos, no accents, regional slang (MX, AR, CO, BR), greetings mixed in. Files: `ml/intent/data/*.jsonl`.
- **Leakage guards**: test is used only for the final numbers (model selection and the threshold use 5-fold CV on train); the script fails on any test phrase that is also in train after normalizing; nearest-train similarity (char 4-gram Jaccard) median 0.23, p90 0.45, one test phrase above 0.8 (0.5%).
- Portuguese is Brazilian; the bank's data has no Brazilian customers, so PT is supported through the phrases only.

### Model
TF-IDF (word 1-2 grams + char_wb 2-4 grams, accents stripped, sublinear tf) + multinomial logistic regression (scikit-learn), C = 100 chosen by 5-fold CV macro-F1 over C ∈ {1 … 1000} × char ranges {2-4, 3-5}. Exported to JSON and run in plain Python in the Lambda (no scikit-learn); a test checks its probabilities match scikit-learn's (max difference 7e-16). Loading the model takes ~25 ms (once per Lambda instance, at the first message); classifying a message ~0.3 ms.

### Results (held-out test, 210 phrases)
| | Accuracy | Macro-F1 | ES macro-F1 | PT macro-F1 |
|---|---|---|---|---|
| Majority class (balanced classes) | 0.143 | 0.036 | | |
| Keyword rules (ES + PT routing words) | 0.629 | 0.618 | 0.608 | 0.628 |
| **TF-IDF + logistic regression** | **0.852** | **0.853** | **0.797** | **0.905** |

Per class F1 (model / keywords): transactional 0.77 / 0.64, product 0.77 / 0.32, complaint 0.81 / 0.54, technical 0.97 / 0.88, commercial 0.88 / 0.62, retention 0.95 / 0.75, other 0.83 / 0.59.

**Calibration and threshold**: expected calibration error 0.07. A prediction counts as confident at probability ≥ 0.58 (the lowest threshold with ≥ 90% precision on out-of-fold train predictions); on test that covers 80% of messages at 92% accuracy. Below it, the hint isn't added and the conversation keeps its previous intent.

**Errors worth knowing** (from the test set): money questions phrased as problems ("me rebotaron la tarjeta", "el ATM no soltó nada") go to complaint; fee questions ("¿qué recargo me ponen si me atraso?") go to complaint; "¿qué me pueden ofrecer para quedarme?" goes to commercial instead of retention; arithmetic or restaurant questions sometimes get a banking label. Spanish is weaker than Portuguese on this test because the Spanish test phrases use more regional slang.

### Limits
- Trained and tested on team-written phrases, not real chats: the numbers show it generalizes across styles we wrote, not to real traffic. The next step is to label real (masked) chat turns from `fh26-chat-interactions`, which already stores each turn's predicted intent.
- Six coarse reasons from the dataset; a message can be two things at once (a complaint about a declined payment); the model picks one.
- The FCR rates come from a synthetic dataset where only the reason matters; they are the bank's averages, not a prediction for this customer.

### Reproduce
```bash
uv run python ml/intent/train.py        # from the repo root: ~30 s, no AWS; writes the model JSON, the parity fixture and metrics.json
cd backend && uv run pytest tests/test_intent.py
```
Rates: `ml/intent/resolution_rates.json` (query inside); numbers above: `ml/intent/metrics.json`.
