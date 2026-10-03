import { t } from '../../i18n/translations';
import type { IdlePhase } from '../../hooks/useIdleTimer';
import './IdlePrompt.css';

interface Props {
  phase: IdlePhase;
  canKeepOpen: boolean;
  onKeepOpen: () => void;
  language: 'es' | 'pt';
}

/** Fixed (not model-generated) "anything else?" question and the "closed due to inactivity" notice. */
export function IdlePrompt({ phase, canKeepOpen, onKeepOpen, language }: Props) {
  return (
    <div className="idle-prompt-region" role="status" aria-live="polite">
      {phase === 'prompt' && (
        <div className="idle-prompt">
          <p>{t('agent.idle.question', language)}</p>
          {canKeepOpen ? (
            <button type="button" className="idle-prompt-keep" onClick={onKeepOpen}>
              {t('agent.idle.keep', language)}
            </button>
          ) : (
            <p>{t('agent.idle.last', language)}</p>
          )}
        </div>
      )}
      {phase === 'closing' && (
        <div className="idle-prompt">
          <p>{t('agent.idle.closed', language)}</p>
        </div>
      )}
    </div>
  );
}
