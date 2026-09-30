## Test Case Info

| Field       | Value        |
|-------------|----------------------------------------------|
| **Use Case**    | UC2 — Resume pending intent |
| **Priority**    | 🟡 Medium |
| **Auth Required** | Yes (same as UC2-TC1) |

## Preconditions

- [ ] New anonymous session
- [ ] Test customer exists in DynamoDB with known document ID, birth date, phone last-4

## Test Steps

1. Send: *"¿Cuánto tengo en mi cuenta?"*
2. Complete the full auth flow (ID, KBA, OTP)

## Expected Result

- [ ] After verification, the agent resumes and answers the original balance question directly
- [ ] The user is not asked to repeat the original question
- [ ] `pending_intent` is cleared after resuming

## Actual Result

<!-- Fill in after execution -->

| Criterion | Expected | Actual | Pass/Fail |
|-----------|----------|--------|-----------|
| Auto-resume | Agent answers balance without re-asking | | |
| No repeat prompt | User not asked to repeat question | | |
| Intent cleared | `pending_intent` is cleared | | |

## Evidence

<!-- Screenshots, logs, or recordings from the test run -->

## Notes

<!-- Any additional observations or context -->
