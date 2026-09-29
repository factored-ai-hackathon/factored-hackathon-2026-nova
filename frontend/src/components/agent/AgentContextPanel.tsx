import { useAgent } from '../../context/AgentContext';
import { useApp } from '../../context/AppContext';
import { t } from '../../i18n/translations';
import { formatPercent } from '../../utils/format';

/**
 * AgentContextPanel — right column in the full agent view.
 *
 * Shows safe, user-facing agent metadata:
 *   - Intent
 *   - Sentiment (with badge)
 *   - Confidence (with progress bar)
 *   - Resolution status
 *   - Recommended action
 *
 * Does NOT expose chain-of-thought or internal reasoning.
 * This data supports EDD: it can be correlated with evaluation results.
 */
export function AgentContextPanel() {
  const { language } = useApp();
  const { conversation } = useAgent();
  const ctx = conversation.agentContext;

  return (
    <aside className="agent-full-right" aria-label={t('agent.agentContext', language)}>
      {/* Header */}
      <div className="full-view-header">
        <span className="full-view-title">{t('agent.agentContext', language)}</span>
      </div>

      {/* Intent */}
      <div className="context-section">
        <div className="context-section-title">{t('agent.intent', language)}</div>
        <div className="context-value">
          {ctx.intent ? t(`intent.${ctx.intent}`, language) : '—'}
        </div>
      </div>

      {/* Sentiment */}
      <div className="context-section">
        <div className="context-section-title">{t('agent.sentiment', language)}</div>
        <span className={`sentiment-badge ${ctx.sentiment}`}>
          {t(`sentiment.${ctx.sentiment}`, language)}
        </span>
      </div>

      {/* Confidence */}
      <div className="context-section">
        <div className="context-section-title">{t('agent.confidence', language)}</div>
        {ctx.confidence > 0 ? (
          <div className="confidence-bar-wrapper">
            <div className="confidence-bar-track" role="meter" aria-valuenow={Math.round(ctx.confidence * 100)} aria-valuemin={0} aria-valuemax={100}>
              <div
                className="confidence-bar-fill"
                style={{ width: `${ctx.confidence * 100}%` }}
              />
            </div>
            <span className="confidence-text">{formatPercent(ctx.confidence)}</span>
          </div>
        ) : (
          <span className="context-value" style={{ color: 'var(--color-text-muted)' }}>—</span>
        )}
      </div>

      {/* Resolution status */}
      <div className="context-section">
        <div className="context-section-title">{t('agent.resolutionStatus', language)}</div>
        <span className={`status-badge ${ctx.status}`}>
          {t(`status.${ctx.status}`, language)}
        </span>
      </div>

      {/* Recommended action */}
      <div className="context-section">
        <div className="context-section-title">{t('agent.recommendedAction', language)}</div>
        <div className="context-value" style={{ fontSize: 'var(--text-sm)', lineHeight: 1.4 }}>
          {ctx.recommendedAction ?? '—'}
        </div>
      </div>

      {/* Conversation ID (for evaluation tracing) */}
      {ctx.conversationId && (
        <div className="context-section">
          <div className="context-section-title">{t('agent.conversationId', language)}</div>
          <div
            className="context-value"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-xs)',
              color: 'var(--color-text-muted)',
              wordBreak: 'break-all',
            }}
          >
            {ctx.conversationId}
          </div>
        </div>
      )}

      {/* Requires human */}
      <div className="context-section">
        <div className="context-section-title">{t('agent.escalationRequired', language)}</div>
        <div className="context-value">
          {ctx.requiresHuman ? (
            <span style={{ color: 'var(--color-warning)', fontWeight: 600 }}>{t('agent.yes', language)}</span>
          ) : (
            <span style={{ color: 'var(--color-success)' }}>{t('agent.no', language)}</span>
          )}
        </div>
      </div>
    </aside>
  );
}
