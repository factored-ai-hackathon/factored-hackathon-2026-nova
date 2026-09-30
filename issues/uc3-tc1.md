## Test Case Info

| Field       | Value        |
|-------------|----------------------------------------------|
| **Use Case**    | UC3 — Credit request, auto-approved |
| **Priority**    | 🔴 High (demo-critical) |
| **Auth Required** | Yes (verified session) |

## Preconditions

- [ ] Verified session
- [ ] Test customer profile scored to land above the approve cut-off

## Test Steps

1. Send: *"Necesito un préstamo de 10 millones para 24 meses"*
2. Provide income, employment and purpose when asked
3. Give explicit consent to score and query the bureau

## Expected Result

- [ ] Pipeline reaches status `APPROVED`
- [ ] Final message includes: amount, rate, term, affordability summary, top 3 SHAP factors in plain language
- [ ] Response time within acceptable range for the demo (flag if pipeline latency is noticeable)

## Actual Result

<!-- Fill in after execution -->

| Criterion | Expected | Actual | Pass/Fail |
|-----------|----------|--------|-----------|
| Status APPROVED | Pipeline status = `APPROVED` | | |
| Complete info | Amount + rate + term + SHAP factors shown | | |
| Latency | Response time acceptable for demo | | |

## Evidence

<!-- Screenshots, logs, or recordings from the test run -->

## Notes

<!-- Any additional observations or context -->
