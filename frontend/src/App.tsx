import { useEffect, useRef, useState } from 'react'
import { ApiError, createSession, sendMessage } from './api/client'
import { ChatWindow } from './components/ChatWindow'
import { Composer } from './components/Composer'
import { LanguageToggle } from './components/LanguageToggle'
import { strings, type Lang } from './i18n'
import type { ChatMessage } from './types'
import './App.css'

export default function App() {
  const [lang, setLang] = useState<Lang>('es')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const sessionRef = useRef<string | null>(null)
  const t = strings[lang]

  useEffect(() => {
    document.documentElement.lang = lang
    document.title = t.title
  }, [lang, t.title])

  function patch(id: string, update: (m: ChatMessage) => Partial<ChatMessage>) {
    setMessages((ms) => ms.map((m) => (m.id === id ? { ...m, ...update(m) } : m)))
  }

  async function getSession(): Promise<string> {
    sessionRef.current ??= await createSession(lang)
    return sessionRef.current
  }

  async function streamInto(replyId: string, text: string) {
    let finished = false
    for await (const event of sendMessage(await getSession(), text, lang)) {
      if (event.type === 'token') patch(replyId, (m) => ({ text: m.text + event.text }))
      else {
        finished = true
        if (event.type === 'error') patch(replyId, () => ({ error: 'errorGeneric' }))
      }
    }
    if (!finished) throw new Error('stream ended without done/error')
  }

  async function send(text: string) {
    const replyId = crypto.randomUUID()
    setMessages((ms) => [
      ...ms,
      { id: crypto.randomUUID(), role: 'user', text },
      { id: replyId, role: 'assistant', text: '', pending: true },
    ])
    setStreaming(true)
    try {
      try {
        await streamInto(replyId, text)
      } catch (err) {
        // The backend keeps sessions in memory; after a restart, start a new one once.
        if (!(err instanceof ApiError && err.status === 404)) throw err
        sessionRef.current = null
        await streamInto(replyId, text)
      }
    } catch (err) {
      console.error(err)
      patch(replyId, () => ({ error: 'errorNetwork' }))
    } finally {
      patch(replyId, () => ({ pending: false }))
      setStreaming(false)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>{t.title}</h1>
          <p className="subtitle">{t.subtitle}</p>
        </div>
        <LanguageToggle lang={lang} t={t} disabled={streaming} onChange={setLang} />
      </header>
      <main className="app-main">
        <ChatWindow messages={messages} t={t} />
      </main>
      <footer className="app-footer">
        <Composer t={t} busy={streaming} onSend={send} />
        <p className="disclaimer">{t.disclaimer}</p>
      </footer>
    </div>
  )
}
