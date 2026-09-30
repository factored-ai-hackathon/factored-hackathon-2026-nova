## Test Case Info

| Field       | Value        |
|-------------|----------------------------------------------|
| **Use Case**    | UC1 — General question (edge case) |
| **Priority**    | 🔴 High |
| **Auth Required** | No |

## Preconditions

- [ ] New anonymous session
- [ ] Question chosen to have no matching content in the KB

## Test Steps

1. Open a new chat session
2. Send a question clearly outside the KB's scope, e.g. *"¿Dan tarjetas de crédito para pagar en criptomonedas?"*

## Expected Result

- [ ] Retrieval score is low
- [ ] Agent explicitly says it doesn't know / can't confirm, rather than fabricating an answer
- [ ] Agent offers to escalate to a human

## Actual Result

<!-- Fill in after execution -->

| Criterion | Expected | Actual | Pass/Fail |
|-----------|----------|--------|-----------|
| Low retrieval score | Score below threshold | | |
| Honest fallback | Agent admits it doesn't know | | |
| Escalation offered | Agent offers human handoff | | |

## Evidence

<!-- Screenshots, logs, or recordings from the test run -->

## Notes

<!-- Any additional observations or context -->
