import { useState } from 'react';
import { Star, X } from 'lucide-react';
import { ApiError } from '../../api/client';
import { rateAdvisor } from '../../services/agentService';
import { loadStored, saveStored } from '../../utils/persist';
import type { HandoffState } from '../../context/AgentContext';
import './SatisfactionPrompt.css';

const TEXTS = {
  es: {
    question: '¿Cómo fue tu experiencia con el asesor?',
    star: (n: number) => `${n} de 5`,
    dismiss: 'Ahora no',
    thanks: '¡Gracias por tu opinión!',
    error: 'No pudimos guardar tu opinión. Inténtalo de nuevo.',
  },
  pt: {
    question: 'Como foi sua experiência com o atendente?',
    star: (n: number) => `${n} de 5`,
    dismiss: 'Agora não',
    thanks: 'Obrigado pela sua avaliação!',
    error: 'Não conseguimos salvar sua avaliação. Tente novamente.',
  },
  en: {
    question: 'How was your experience with the advisor?',
    star: (n: number) => `${n} out of 5`,
    dismiss: 'Not now',
    thanks: 'Thanks for your feedback!',
    error: "We couldn't save your rating. Please try again.",
  },
};

type Phase = 'asking' | 'sending' | 'thanks' | 'dismissed';

const doneKey = (caseId: string) => `rated.${caseId}`;

/**
 * After the human agent closes the case: "How was your experience with the advisor?", 1 to 5.
 * Shown once per closed case (an answer or a dismissal is remembered for the browser session).
 */
export function SatisfactionPrompt({ handoff, language }: { handoff: HandoffState | null; language: string }) {
  const caseId = handoff?.status === 'closed' ? handoff.caseId : '';
  const [phases, setPhases] = useState<Record<string, Phase>>({});
  const [failed, setFailed] = useState(false);
  if (!caseId) return null;

  const texts = language === 'es' || language === 'pt' ? TEXTS[language] : TEXTS.en;
  const phase: Phase = phases[caseId] ?? (loadStored<string>(doneKey(caseId)) ? 'dismissed' : 'asking');
  const finish = (next: Phase, remember: boolean) => {
    if (remember) saveStored(doneKey(caseId), next);
    setPhases((p) => ({ ...p, [caseId]: next }));
  };

  if (phase === 'dismissed') return null;
  if (phase === 'thanks') {
    return (
      <p className="satisfaction-thanks" role="status">
        {texts.thanks}
      </p>
    );
  }

  const submit = async (rating: number) => {
    if (phase === 'sending') return; // once per case
    setFailed(false);
    setPhases((p) => ({ ...p, [caseId]: 'sending' }));
    try {
      await rateAdvisor(rating);
      finish('thanks', true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) finish('thanks', true); // already rated
      else {
        setFailed(true);
        setPhases((p) => ({ ...p, [caseId]: 'asking' }));
      }
    }
  };

  return (
    <div className="satisfaction" role="group" aria-labelledby="satisfaction-question">
      <div className="satisfaction-head">
        <p id="satisfaction-question">{texts.question}</p>
        <button type="button" className="satisfaction-dismiss" aria-label={texts.dismiss} title={texts.dismiss} onClick={() => finish('dismissed', true)}>
          <X size={16} aria-hidden="true" />
        </button>
      </div>
      <div className="satisfaction-stars">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            className="satisfaction-star"
            aria-label={texts.star(n)}
            title={texts.star(n)}
            disabled={phase === 'sending'}
            onClick={() => void submit(n)}
          >
            <Star size={24} aria-hidden="true" />
            <span className="satisfaction-n" aria-hidden="true">{n}</span>
          </button>
        ))}
      </div>
      {failed && <p className="satisfaction-error" role="alert">{texts.error}</p>}
    </div>
  );
}
