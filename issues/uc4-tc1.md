## Test Case Info

| Field       | Value        |
|-------------|----------------------------------------------|
| **Use Case**    | UC4 — Credit request, rejected |
| **Priority**    | 🔴 High |
| **Auth Required** | Yes (verified session) |

## Preconditions

- [ ] Verified session
- [ ] Test customer profile scored to land below the reject cut-off

## Test Steps

1. Same flow as UC3-TC1 with a low-capacity-to-pay profile

## Expected Result

- [ ] Pipeline reaches status `REJECTED`
- [ ] Explanation is respectful, states the main contributing factors, and suggests what could improve the outcome
- [ ] Agent offers the option to talk to a human advisor

## Actual Result

<!-- Fill in after execution -->

| Criterion | Expected | Actual | Pass/Fail |
|-----------|----------|--------|-----------|
| Status REJECTED | Pipeline status = `REJECTED` | | |
| Respectful explanation | Factors + improvement suggestions | | |
| Human advisor offer | Agent offers human handoff | | |

## Evidence

<!-- Screenshots, logs, or recordings from the test run -->

## Notes

<!-- Any additional observations or context -->
