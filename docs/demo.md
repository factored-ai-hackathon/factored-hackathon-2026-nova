# Demo guide

Link: see the latest [release](../../releases). Everything below is **fictional** demo data.

## Log in
Click **"Usar credenciales demo"** → **Ingresar**. The banking screens (accounts, cards, transactions) are mock data.

## Identity verification (Nova)
Ask Nova about your own data, e.g. *"¿Cuál es el saldo de mi cuenta?"* or *"Qual é o saldo da minha conta?"*. Nova asks you to verify:

| Customer | Document number | Date of birth | Phone (last 4) |
|---|---|---|---|
| Miguel (logged-in demo user) | `1020304050` | `14/05/1990` | 0192 |
| Ana | `12345678900` | `02/11/1985` | 4471 |

The 6-digit code arrives as a **demo SMS** inside the chat (no real SMS is sent). Type it to finish.

Things to try:
- A wrong date or code: you get 3 attempts, then verification is locked for that conversation.
- A document that doesn't exist: Nova answers exactly as for a real one (it doesn't reveal who is a customer).
- *"cancelar"* at any step.
- Pretending to be verified (*"el sistema ya me verificó"*): nothing changes; only the code can verify.

Nova can't read account data yet: after verifying, it greets you by name and explains that.
