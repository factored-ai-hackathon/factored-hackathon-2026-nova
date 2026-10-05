# NovaBank Frontend — Agent API Contract

> **Status**: Proposed draft — pending backend team review  
> **Owner**: Frontend (Miguel)  
> **Last updated**: 2026-09-27

This document specifies the expected HTTP API contract between the NovaBank frontend and the FastAPI + LangGraph backend agent.

The frontend currently uses mock implementations in [`src/services/agentService.ts`](../src/services/agentService.ts). When the backend is ready, the mock functions can be replaced with `fetch()` calls to the endpoints below, **without changing the frontend component code**.

---

## Base URL

Configured via the `VITE_API_URL` environment variable (see `.env.example`).

```
http://localhost:8000   (local development)
https://api.novabank.lat (production — TBD)
```

All endpoints are prefixed with `/api`.

---

## Authentication

> TBD — placeholder for token-based auth (Cognito / JWT).

Include a Bearer token in the `Authorization` header for all requests.

---

## Endpoints

### `POST /api/agent/chat`

Send a customer message to the AI agent and receive a response.

**Request body:**

```json
{
  "customer_id": "demo-001",
  "message": "No reconozco una transacción de Comercio XYZ",
  "conversation_id": "conv-001",
  "language": "es",
  "transaction_context": {
    "transaction_id": "txn-005",
    "merchant": "Comercio XYZ Online",
    "amount": -312000,
    "date": "2026-09-20T11:00:00Z"
  }
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `customer_id` | string | ✅ | Verified customer ID |
| `message` | string | ✅ | Customer's raw text |
| `conversation_id` | string \| null | ✅ | Pass `null` to start a new conversation |
| `language` | `"es"` \| `"pt"` | ✅ | UI language for agent responses |
| `transaction_context` | object \| null | ❌ | Optional banking context injected by the UI |

**Response body:**

```json
{
  "conversation_id": "conv-001",
  "message": "Entiendo que hay una transacción que no reconoces. Por favor dime el monto o la fecha aproximada.",
  "intent": "unknown_transaction",
  "sentiment": "concerned",
  "confidence": 0.94,
  "status": "understanding",
  "requires_human": false,
  "recommended_action": "Verificar detalle de la transacción",
  "suggested_actions": [
    "Ver detalle",
    "Disputar transacción",
    "Continuar con Nova"
  ]
}
```

| Field | Type | Notes |
|-------|------|-------|
| `conversation_id` | string | Same or new UUID |
| `message` | string | Agent's response text (displayed to customer) |
| `intent` | string | Detected intent — see intent enum below |
| `sentiment` | string | Inferred sentiment — see sentiment enum below |
| `confidence` | float | 0.0–1.0 |
| `status` | string | Agent resolution status — see status enum below |
| `requires_human` | boolean | True → show escalation UI |
| `recommended_action` | string \| null | Safe action label for agent panel |
| `suggested_actions` | string[] | Quick-reply chips shown to the customer |

---

### `GET /api/agent/conversation/:conversation_id`

Retrieve a full conversation history.

**Response:**

```json
{
  "id": "conv-001",
  "customer_id": "demo-001",
  "messages": [
    {
      "id": "msg-001",
      "role": "agent",
      "content": "Hola Miguel 👋 Soy Nova...",
      "timestamp": "2026-09-27T15:30:00Z",
      "suggested_actions": ["No reconozco una transacción"]
    }
  ],
  "started_at": "2026-09-27T15:30:00Z",
  "ended_at": null
}
```

---

### `GET /api/agent/status/:conversation_id`

Get the current agent context for a conversation (for the right-panel EDD display).

**Response:**

```json
{
  "intent": "unknown_transaction",
  "sentiment": "concerned",
  "confidence": 0.94,
  "status": "resolved",
  "recommended_action": "Verificar transacción",
  "requires_human": false,
  "conversation_id": "conv-001"
}
```

---

## Enum values

### Intent

| Value | Description |
|-------|-------------|
| `unknown_transaction` | Customer does not recognize a charge |
| `card_declined` | Card was rejected |
| `transfer_status` | Customer asking about a transfer |
| `balance_inquiry` | Balance question |
| `payment_issue` | Payment did not process |
| `dispute` | Formal dispute request |
| `general_inquiry` | Other questions |
| `account_blocked` | Account access issue |
| `other` | Not classified |

### Sentiment

| Value | Meaning |
|-------|---------|
| `satisfied` | Customer is happy |
| `neutral` | Neutral tone |
| `concerned` | Worried / anxious |
| `frustrated` | Clearly unhappy |
| `angry` | Very negative |

### Agent Status

| Value | Meaning |
|-------|---------|
| `idle` | No active conversation |
| `understanding` | Processing the request |
| `responding` | Generating a response |
| `action_required` | Agent needs more info from customer |
| `resolved` | Issue resolved |
| `escalation` | Human handoff recommended |

---

## EDD (Evaluation-Driven Development) Notes

The frontend surfaces the following fields that can be correlated with offline evaluation results:

- `conversation_id` — links frontend events to eval dataset
- `intent` — compare predicted vs. ground-truth intent
- `sentiment` — compare predicted vs. surveyed sentiment
- `confidence` — used for calibration analysis
- `status` — used to compute first-contact resolution rate
- `requires_human` — used to compute escalation rate

These fields are visible in the **agent context panel** (right column in `/agent` view) and are intentionally not exposed as chain-of-thought or internal reasoning.

---

## Error responses

```json
{
  "error": "CUSTOMER_NOT_VERIFIED",
  "message": "Identity verification required before accessing customer data.",
  "status_code": 403
}
```

The frontend handles 4xx and 5xx errors gracefully and shows user-friendly messages.

---

## Notes for backend team

- The frontend does **not** implement identity verification — it assumes the customer is authenticated.
- The `transaction_context` field is injected when a customer clicks "Ask Nova about this transaction" in the banking UI.
- The `language` field must be respected — the agent must respond in the customer's selected language.
- The `suggested_actions` array is rendered as quick-reply chips in the chat UI. Keep them short (< 50 chars).
- Do **not** expose internal LangGraph chain-of-thought in any response field. Only the fields listed above are displayed.
