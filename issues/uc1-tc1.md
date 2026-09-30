## Test Case Info

| Field       | Value        |
|-------------|----------------------------------------------|
| **Use Case**    | UC1 — General question |
| **Priority**    | 🔴 High (demo-critical) |
| **Auth Required** | No |

## Preconditions

- [ ] New anonymous session (`auth_status = anonymous`, no `customer_id`)
- [ ] KB contains documentation on account opening requirements

## Test Steps

1. Open a new chat session
2. Send: *"¿Qué documentos necesito para abrir una cuenta de ahorros?"*

## Expected Result

- [ ] Agent answers directly, citing at least one KB source
- [ ] No authentication is requested at any point
- [ ] `auth_status` remains `anonymous` after the exchange
- [ ] No protected tool (`get_accounts`, `get_balances`, etc.) is invoked

## Actual Result

<!-- Fill in after execution -->

| Criterion | Expected | Actual | Pass/Fail |
|-----------|----------|--------|-----------|
| KB-sourced answer | Agent cites ≥1 KB source | | |
| No auth prompt | No authentication requested | | |
| Status unchanged | `auth_status = anonymous` | | |
| No protected tools | No `get_accounts`/`get_balances` calls | | |

## Evidence

<!-- Screenshots, logs, or recordings from the test run -->

## Notes

<!-- Any additional observations or context -->
