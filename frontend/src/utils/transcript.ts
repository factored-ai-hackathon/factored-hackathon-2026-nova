// The conversation as plain text, to download or send by email (chat header buttons).
import type { ConversationMessage, Language } from '../types';
import { t } from '../i18n/translations';

const MAILTO_MAX = 1800; // mail clients cut long mailto: links

function speaker(m: ConversationMessage, customerName: string, language: Language): string {
  if (m.role === 'user') return customerName || t('transcript.you', language);
  if (m.role === 'human') return `${m.author ?? t('transcript.agent', language)} (${t('transcript.agent', language)})`;
  if (m.role === 'system') return t('transcript.notice', language);
  return 'Nova';
}

export function transcriptText(
  messages: ConversationMessage[],
  customerName: string,
  language: Language,
): string {
  const locale = language === 'pt' ? 'pt-BR' : 'es-CO';
  const header = `${t('transcript.title', language)} · ${new Date().toLocaleString(locale)}`;
  const lines = messages
    .filter((m) => m.content.trim())
    .map((m) => {
      const when = new Date(m.timestamp).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' });
      return `[${when}] ${speaker(m, customerName, language)}:\n${m.content.trim()}`;
    });
  return [header, '', ...lines].join('\n\n');
}

export function transcriptFileName(date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  const stamp = `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}`;
  return `conversacion-nova-${stamp}.txt`;
}

export function downloadTranscript(text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = transcriptFileName();
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** A mailto: link with the conversation (cut if too long: the download has all of it). */
export function transcriptMailto(text: string, language: Language): string {
  const cut = text.length > MAILTO_MAX ? `${text.slice(0, MAILTO_MAX)}\n\n${t('transcript.cut', language)}` : text;
  const subject = t('transcript.title', language);
  return `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(cut)}`;
}
