import type { Lang, Strings } from '../i18n'

type Props = { lang: Lang; t: Strings; disabled: boolean; onChange: (lang: Lang) => void }

const OPTIONS: { value: Lang; label: string }[] = [
  { value: 'es', label: 'ES' },
  { value: 'pt', label: 'PT' },
]

export function LanguageToggle({ lang, t, disabled, onChange }: Props) {
  return (
    <div className="lang-toggle" role="group" aria-label={t.language}>
      {OPTIONS.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={lang === o.value}
          disabled={disabled}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
