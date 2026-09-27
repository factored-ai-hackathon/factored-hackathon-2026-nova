import { useEffect, useRef } from 'react'
import type { Strings } from '../i18n'
import type { ChatMessage } from '../types'
import { MessageBubble } from './MessageBubble'

type Props = { messages: ChatMessage[]; t: Strings }

export function ChatWindow({ messages, t }: Props) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages])

  return (
    <div className="chat-window" role="log" aria-live="polite">
      <MessageBubble message={{ id: 'welcome', role: 'assistant', text: t.welcome }} t={t} />
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} t={t} />
      ))}
      <div ref={endRef} />
    </div>
  )
}
