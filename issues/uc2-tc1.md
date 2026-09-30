## Test Case Info

| Field       | Value        |
|-------------|----------------------------------------------|
| **Use Case**    | UC2 — Balance and movements |
| **Priority**    | 🔴 High (demo-critical) |
| **Auth Required** | Yes (full 3-step) |

## Preconditions

- [ ] New anonymous session
- [ ] Test customer exists in DynamoDB with known document ID, birth date, phone last-4

## Test Steps

1. Send: *"¿Cuánto tengo en mi cuenta?"*
2. Confirm the agent blocks and starts the auth subgraph
3. Provide document type + number
4. Provide the two KBA fields (birth date, phone last-4)
5. Provide the OTP code received

## Expected Result

- [ ] `get_balances` is not called until `auth_status = verified`
- [ ] All three auth steps are required in order (no skip)
- [ ] Final answer shows the balance with the account number masked
- [ ] `customer_id` is bound to the session, never asked again in the conversation

## Actual Result

<!-- Fill in after execution -->

| Criterion | Expected | Actual | Pass/Fail |
|-----------|----------|--------|-----------|
| Auth gate | `get_balances` blocked until verified | | |
| Step order | ID → KBA → OTP (no skip) | | |
| Account masking | Account number is masked | | |
| Session binding | `customer_id` persists, not re-asked | | |

## Evidence

<!-- Screenshots, logs, or recordings from the test run -->

## Notes

<!-- Any additional observations or context -->
