# Data findings

What the LATAM Bank data actually shows, from queries on `latam_curated` (Sep 27, 2026). Add new findings at the bottom.

## Headline
**The reason for contact drives resolution; almost nothing else does.** Complaints are resolved least often.

| Reason (`reason_category`) | Resolved on the contact |
|---|---|
| Producto | ~88–90% |
| Comercial | ~65% |
| Retención | ~61% |
| **Queja** (complaint) | **~43%** |
| Técnico, Transaccional | not checked yet |

## What does *not* affect resolution
| Factor | Result |
|---|---|
| Channel (phone, app, WhatsApp, email, chat, web) | 76–77% everywhere |
| Agent experience (Junior → Specialist) | 75–79%, no pattern |
| Customer/agent accent match | No effect. About a third of interactions have no detected customer accent |
| Customer sentiment (within a reason) | No effect |
| Escalation | ~10% in every group: looks random |

## First contact resolution (FCR)
- FCR (`is_fcr`) = resolved and no repeat contact on the same topic within 7 days.
- FCR ≈ resolved (~76.0% vs ~76.6%): repeat contacts are rare in this data. The metric is correct but won't be a headline.

## Data quality
| Issue | What we did |
|---|---|
| Every transcript's text has line breaks, so Athena split 171k transcripts into ~925k broken rows | Read transcripts from a Parquet copy (`data/scripts/convert_transcripts.py`) |
| Complaints never link to interactions (`origin_interaction_id` is empty on all 67,095) | Complaints are analysed on their own (`stg_complaints`) |
| `contact_reason` repeats `reason_category` for complaints | Use `reason_category` |
| Real counts differ from the dataset summary: 686,296 interactions (not 800k), 171,321 transcripts (not 200k), 4,425,008 transactions (not 5M); 400,000 products as announced | Use the real counts in slides |
| No orphaned keys between interactions, customers, agents and dates (tests pass) | Nothing needed |

## What it means for the project (for the team to decide)
1. A model that predicts resolution would mostly learn "complaints resolve less"; SQL already shows that. Weak ML story.
2. **Complaints are the biggest opportunity** (43% vs ~90% for product questions): a strong, data-backed candidate for the demo flow.
3. ML that adds value: **understanding the customer's message** (intent/reason classification in Spanish and Portuguese). ~~Trained on the 171k transcripts~~: checked Sep 30, the transcripts can't train it (next section); built on team-written phrases instead (decision 29, `ml/README.md`).
4. Checked Sep 30: complaints on their own (`sla_breached` ~20%, `resolution_days` ~15.6 for every priority, category and case type) and fraud (next section) have no learnable pattern either.

## What the data can't teach (checked Sep 30)
| Target | Finding |
|---|---|
| Reason from `call_transcripts.customer_text` | Only 42 distinct texts in 171,321 transcripts, each spread over all 6 reasons in the same proportions; `detected_intents` is `consulta_general` or empty everywhere |
| Resolution from the transcript text | 76-77% for every text |
| `is_fraud` | 0.1% positives, flat by amount, channel, hour, merchant category and type; `fraud_score` > 40 is always fraud, below 30 almost never |
| Complaint SLA breach / resolution days | Same ~20% / ~15.6 days for every priority, category and case type |
| Resolution from the customer's contact history | 76-77% whatever the number or outcome of previous contacts |

## Reproduce
Athena console → workgroup `hackathon`, for example:
```sql
SELECT reason_category,
       count(*) AS n,
       avg(CASE WHEN was_resolved THEN 1.0 ELSE 0 END) AS resolved_rate,
       avg(CASE WHEN is_fcr THEN 1.0 WHEN NOT is_fcr THEN 0 END) AS fcr_rate,  -- ignores rows where FCR can't be judged
       avg(CASE WHEN was_escalated THEN 1.0 ELSE 0 END) AS escalation_rate
FROM latam_curated.fact_interaction
GROUP BY 1 ORDER BY resolved_rate DESC;
```
