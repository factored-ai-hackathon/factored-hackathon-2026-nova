import { useAgent } from '../../context/AgentContext';
import { useApp } from '../../context/AppContext';
import { t } from '../../i18n/translations';
import { MessageCircle, X } from 'lucide-react';

export function AgentFAB() {
  const { language } = useApp();
  const { isOpen, openAgent, closeAgent } = useAgent();

  return (
    <div className="agent-fab">
      <span className="agent-fab-label">{t('agent.talking', language)}</span>
      {!isOpen && <span className="agent-fab-pulse" aria-hidden="true" />}
      <button
        className={`agent-fab-btn${isOpen ? ' active' : ''}`}
        onClick={() => (isOpen ? closeAgent() : openAgent())}
        aria-label={isOpen ? t('agent.close', language) : t('agent.open', language)}
        aria-expanded={isOpen}
      >
        {isOpen ? <X size={22} /> : <MessageCircle size={22} />}
      </button>
    </div>
  );
}
