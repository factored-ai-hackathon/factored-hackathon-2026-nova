import type { Strings } from '../i18n'
import type { ChatMessage } from '../types'

type Props = { message: ChatMessage; t: Strings }

export function MessageBubble({ message, t }: Props) {
  const who = message.role === 'user' ? t.you : t.assistant
  return (
    <div className={`bubble-row ${message.role}`}>
      <div className="bubble" aria-label={who} aria-busy={message.pending}>
        {message.text || (message.pending && <span className="typing" aria-label={t.sending} />)}
        {message.error && <p className="bubble-error" role="alert">{t[message.error]}</p>}
      </div>
    </div>
  )
}
