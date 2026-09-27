import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { MAX_TEXT_CHARS } from '../api/client'
import type { Strings } from '../i18n'

type Props = { t: Strings; busy: boolean; onSend: (text: string) => void }

export function Composer({ t, busy, onSend }: Props) {
  const [text, setText] = useState('')
  const canSend = !busy && text.trim().length > 0

  function submit(e?: FormEvent) {
    e?.preventDefault()
    if (!canSend) return
    onSend(text.trim())
    setText('')
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) submit(e)
  }

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={t.placeholder}
        aria-label={t.placeholder}
        maxLength={MAX_TEXT_CHARS}
        rows={1}
      />
      <button type="submit" disabled={!canSend}>
        {busy ? t.sending : t.send}
      </button>
    </form>
  )
}
