// Human agent console API (docs/api-contract.md). The key goes in the body: CloudFront only
// forwards a few headers to the API.
import { ApiError } from './client'

export type CaseStatus = 'waiting' | 'active' | 'closed'

export interface CaseSummary {
  case_id: string
  status: CaseStatus
  created_at: string
  reason: string
  summary: string
  lang: 'es' | 'pt'
  agent_name: string | null
  customer: string | null
  /** The intent classifier's label for the conversation (backend/app/agent/intent.py). */
  intent?: string | null
  faithfulness?: number | null
  /** The customer's 1-5 rating of the advisor, null until rated. */
  rating?: number | null
}

export interface CaseIntent {
  label: string
  confidence: number
  reason_category: string | null
  fcr_rate: number | null
  confident: boolean
  early_handoff: boolean
}

export interface QueueStats {
  waiting: number
  active: number
  closed: number
  faithfulness_avg: number | null
  /** Mean customer rating of the advisor (1-5) and how many cases were rated. */
  satisfaction_avg?: number | null
  rated?: number
}

/** How Nova's answers match the data it consulted (backend/app/agent/faithfulness.py). */
export interface Faithfulness {
  evidence: { tool: string; args: Record<string, unknown>; at: string }[]
  answers: {
    index: number
    text: string
    claims: { token: string; text: string; supported: boolean }[]
    score: number | null
    sentences: { text: string; similarity: number[]; shared: string[][] }[]
  }[]
  overall: number | null
}

export interface CaseDetail extends Omit<CaseSummary, 'faithfulness' | 'intent'> {
  intent: CaseIntent | null
  open_questions: string[]
  verified_facts: {
    identity_verified: boolean
    customer_id: string | null
    first_name: string | null
    logged_in_customer_id: string | null
  }
  evidence: { tool: string; args: Record<string, unknown>; result: string; at: string }[]
  transcript: { role: 'customer' | 'assistant'; text: string }[]
  messages: { from: 'customer' | 'agent' | 'system'; text: string; at: string }[]
  faithfulness?: Faithfulness
}

const BASE_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

async function post<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${BASE_URL}/v1/agent${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let code: string | undefined
    try {
      code = (await res.json()).detail
    } catch {
      // not JSON
    }
    throw new ApiError(res.status, `agent console ${path} failed: ${res.status}`, code)
  }
  return res.json()
}

export const listCases = (key: string) => post<{ cases: CaseSummary[]; stats?: QueueStats }>('/cases', { key })
export const getCase = (key: string, id: string) => post<CaseDetail>(`/cases/${encodeURIComponent(id)}`, { key })
export const takeCase = (key: string, id: string, agentName: string) =>
  post<CaseDetail>(`/cases/${encodeURIComponent(id)}/take`, { key, agent_name: agentName })
export const replyCase = (key: string, id: string, text: string) =>
  post<CaseDetail>(`/cases/${encodeURIComponent(id)}/reply`, { key, text })
export const closeCase = (key: string, id: string) =>
  post<CaseDetail>(`/cases/${encodeURIComponent(id)}/close`, { key })
