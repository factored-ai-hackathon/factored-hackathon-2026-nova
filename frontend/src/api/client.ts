// Chat API client. Contract: docs/api-contract.md
import type { Language as Lang } from '../types'

export type StreamEvent =
  | { type: 'token'; text: string }
  | { type: 'done'; messageId: string }
  | { type: 'error'; code: string; message: string }

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const MAX_TEXT_CHARS = 2000

const BASE_URL = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export async function createSession(lang: Lang): Promise<string> {
  const res = await fetch(`${BASE_URL}/v1/chat/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lang }),
  })
  if (!res.ok) throw new ApiError(res.status, `create session failed: ${res.status}`)
  const body: { session_id: string } = await res.json()
  return body.session_id
}

/** POST a message and yield the SSE events (EventSource can't POST, so we read the body). */
export async function* sendMessage(
  sessionId: string,
  text: string,
  lang: Lang,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${BASE_URL}/v1/chat/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ text, lang }),
    signal,
  })
  if (!res.ok || !res.body) throw new ApiError(res.status, `send message failed: ${res.status}`)

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const event = parseEvent(block)
      if (event) yield event
    }
  }
  const last = parseEvent(buffer)
  if (last) yield last
}

function parseEvent(block: string): StreamEvent | null {
  let name = ''
  const data: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) name = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  if (!name || data.length === 0) return null // comments / pings
  const payload = JSON.parse(data.join('\n'))
  switch (name) {
    case 'token':
      return { type: 'token', text: payload.text }
    case 'done':
      return { type: 'done', messageId: payload.message_id }
    case 'error':
      return { type: 'error', code: payload.code, message: payload.message }
    default:
      return null
  }
}
