## Test Case Info

| Field       | Value        |
|-------------|----------------------------------------------|
| **Use Case**    | UC5 — Credit request, grey band |
| **Priority**    | 🟡 Medium |
| **Auth Required** | Yes (verified session) |

## Preconditions

- [ ] Verified session
- [ ] Test customer profile scored between the approve and reject cut-offs

## Test Steps

1. Same flow as UC3-TC1 with a borderline profile
2. Have a credit analyst resolve the review task in Amazon Connect

## Expected Result

- [ ] Pipeline status reaches `REVIEW`, routes to `review-q` → Connect task
- [ ] Customer is told the application is under review (not approved/rejected yet)
- [ ] After the analyst submits a decision via `POST /review`, the customer is notified with the final outcome

## Actual Result

<!-- Fill in after execution -->

| Criterion | Expected | Actual | Pass/Fail |
|-----------|----------|--------|-----------|
| Status REVIEW | Pipeline status = `REVIEW` | | |
| Under review message | Customer told application is under review | | |
| Analyst resolution | POST /review triggers final notification | | |

## Evidence

<!-- Screenshots, logs, or recordings from the test run -->

## Notes

<!-- Any additional observations or context -->
