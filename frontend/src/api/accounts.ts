// The logged-in customer's accounts (POST /v1/accounts/overview, docs/api-contract.md).
import { ApiError } from './client'

export interface OverviewProduct {
  product_id: string
  product_type?: string
  product_number_last4?: string
  currency?: string
  current_balance?: number
  credit_limit?: number
  product_status?: string
  days_past_due?: number
}

export interface OverviewTransaction {
  transaction_at: string // "YYYY-MM-DD HH:MM:SS"
  transaction_type?: string
  transaction_category?: string
  amount?: number
  currency?: string
  merchant_name?: string
  transaction_status?: string
  response_code?: string
  product_id?: string
}

export interface Overview {
  data_as_of: string
  products: OverviewProduct[]
  recent_transactions: OverviewTransaction[]
  open_complaints: number
}

const BASE_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export async function getOverview(sessionId: string): Promise<Overview> {
  const res = await fetch(`${BASE_URL}/v1/accounts/overview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  })
  if (!res.ok) throw new ApiError(res.status, `accounts overview failed: ${res.status}`)
  return res.json()
}
