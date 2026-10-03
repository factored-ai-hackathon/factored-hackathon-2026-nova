// Live metrics for /modelos: aggregates over the deployed traffic (docs/api-contract.md,
// GET /v1/metrics/live). Numbers and labels only: no text, no ids.
import { ApiError } from './client'

export interface Percentiles {
  p50: number | null
  p95: number | null
  n: number
}

export interface Group {
  turns: number
  conversations: number
}

export interface Faithfulness {
  cases: number
  scored: number
  mean: number | null
  claims: { supported: number; total: number; rate: number | null }
  buckets: { all: number; most: number; low: number }
  window: { first: string | null; last: string | null }
  limit: number
}

export interface Satisfaction {
  rated: number
  mean: number | null
  /** Ratings per score, keys "1" to "5". */
  distribution: Record<string, number>
  window: { first: string | null; last: string | null }
}

export interface LiveMetrics {
  turns: number
  conversations: number
  window: { first: string | null; last: string | null }
  errors: number
  error_rate: number | null
  tokens: { input_per_conversation: number | null; output_per_conversation: number | null }
  cost: {
    per_conversation: number | null
    per_1000_conversations: number | null
    per_1000_turns: number | null
    price_per_mtok: { input: number; output: number }
  }
  latency_ms: { total: Percentiles; first_token: Percentiles }
  intent: {
    classified: number
    distribution: Record<string, number>
    confident_share: number | null
    threshold: number
  }
  by_lang: Record<string, Group>
  by_channel: Record<string, Group>
  faithfulness?: Faithfulness
  satisfaction?: Satisfaction
  generated_at: string
  cache_seconds: number
}

const BASE_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export async function getLiveMetrics(signal?: AbortSignal): Promise<LiveMetrics> {
  const res = await fetch(`${BASE_URL}/v1/metrics/live`, { signal })
  if (!res.ok) throw new ApiError(res.status, `live metrics failed: ${res.status}`)
  return res.json()
}
