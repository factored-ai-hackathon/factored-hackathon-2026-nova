import { ThumbsDown, ThumbsUp } from 'lucide-react';
import clsx from 'clsx';
import { useAgent } from '../../context/AgentContext';
import { t } from '../../i18n/translations';
import type { ConversationMessage, Language, Rating } from '../../types';

/** 👍/👎 under an agent reply. Only replies stored by the backend can be rated. */
export function FeedbackButtons({ message, language }: { message: ConversationMessage; language: Language }) {
  const { rateMessage } = useAgent();
  if (message.role !== 'agent' || !message.serverMessageId) return null;

  const button = (rating: Rating, Icon: typeof ThumbsUp, label: string) => (
    <button
      type="button"
      className={clsx('feedback-btn', message.feedback === rating && 'selected')}
      aria-label={label}
      aria-pressed={message.feedback === rating}
      title={label}
      onClick={() => rateMessage(message.id, rating)}
    >
      <Icon size={14} aria-hidden="true" />
    </button>
  );

  return (
    <div className="msg-feedback" role="group" aria-label={t('agent.feedback.question', language)}>
      {button('up', ThumbsUp, t('agent.feedback.up', language))}
      {button('down', ThumbsDown, t('agent.feedback.down', language))}
      {message.feedback && <span className="feedback-thanks">{t('agent.feedback.thanks', language)}</span>}
    </div>
  );
}
