## Test Case Info

| Field       | Value        |
|-------------|----------------------------------------------|
| **Use Case**    | Escalation signal — low-confidence streak |
| **Priority**    | ⚪ Blocked |
| **Auth Required** | N/A |

> [!WARNING]
> **Status: Blocked** — No node currently computes this signal. Do not execute until the output-hook counter is implemented. (Spec gap, finding F7 in diagram review)

## Preconditions

- [ ] Output-hook counter is implemented (currently blocked)

## Test Steps (once implemented)

1. Ask two consecutive questions that each produce a low-retrieval-score or low-groundedness answer

## Expected Result

- [ ] After the 2nd weak answer, Escalation node fires automatically

## Actual Result

<!-- Fill in after execution -->

| Criterion | Expected | Actual | Pass/Fail |
|-----------|----------|--------|-----------|
| Auto-escalation | Escalation node fires after 2nd weak answer | | |

## Evidence

<!-- Screenshots, logs, or recordings from the test run -->

## Notes

<!-- Any additional observations or context -->
