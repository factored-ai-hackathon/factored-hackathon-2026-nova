## Test Case Info

| Field       | Value        |
|-------------|----------------------------------------------|
| **Use Case**    | UC6 — Failed authentication |
| **Priority**    | 🔴 High (demo-critical) |
| **Auth Required** | Yes (will fail) |

## Preconditions

- [ ] New anonymous session
- [ ] Test customer exists with known correct KBA answers

## Test Steps

1. Send: *"¿Cuánto tengo en mi cuenta?"*
2. Provide document ID correctly
3. Provide an incorrect birth date three times in a row

## Expected Result

- [ ] After the 3rd failure, session locks for 15 minutes
- [ ] Agent never reveals which specific field was wrong
- [ ] Escalation node triggers, offering a human handoff
- [ ] No personal data is revealed at any point

## Actual Result

<!-- Fill in after execution -->

| Criterion | Expected | Actual | Pass/Fail |
|-----------|----------|--------|-----------|
| Session lock | Locks after 3 failures for 15 min | | |
| No field leak | Agent doesn't reveal which field was wrong | | |
| Escalation | Human handoff offered | | |
| No data leak | No personal data revealed | | |

## Evidence

<!-- Screenshots, logs, or recordings from the test run -->

## Notes

<!-- Any additional observations or context -->
