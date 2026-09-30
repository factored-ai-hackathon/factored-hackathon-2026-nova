## Test Case Info

| Field       | Value        |
|-------------|----------------------------------------------|
| **Use Case**    | UC7 — Explicit human request |
| **Priority**    | 🟡 Medium |
| **Auth Required** | No |

## Preconditions

- [ ] New anonymous session (auth not required for this path)

## Test Steps

1. Send: *"Quiero hablar con una persona"*

## Expected Result

- [ ] Agent calls `escalate_to_human` directly, no auth subgraph triggered
- [ ] Amazon Connect chat starts with a summary attached (who, auth status, intent, what was tried)

## Actual Result

<!-- Fill in after execution -->

| Criterion | Expected | Actual | Pass/Fail |
|-----------|----------|--------|-----------|
| Direct escalation | `escalate_to_human` called, no auth | | |
| Connect summary | Chat starts with context summary | | |

## Evidence

<!-- Screenshots, logs, or recordings from the test run -->

## Notes

<!-- Any additional observations or context -->
