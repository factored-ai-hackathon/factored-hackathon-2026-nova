// ============================================================
// Formatting utilities
// ============================================================

export function formatCurrency(
  amount: number,
  currency: string = 'COP',
  locale: string = 'es-CO'
): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatDate(
  isoString: string,
  locale: string = 'es-CO'
): string {
  return new Intl.DateTimeFormat(locale, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(new Date(isoString));
}

export function formatTime(isoString: string, locale: string = 'es-CO'): string {
  return new Intl.DateTimeFormat(locale, {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(isoString));
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function maskAccountNumber(number: string): string {
  return number.startsWith('****') ? number : `****${number.slice(-4)}`;
}

// Map internal intent key to display label (Spanish)
export const INTENT_LABELS: Record<string, string> = {
  unknown_transaction: 'Transacción no reconocida',
  card_declined: 'Tarjeta rechazada',
  transfer_status: 'Estado de transferencia',
  balance_inquiry: 'Consulta de saldo',
  payment_issue: 'Problema de pago',
  dispute: 'Disputa',
  general_inquiry: 'Consulta general',
  account_blocked: 'Cuenta bloqueada',
  other: 'Otra consulta',
};

export const SENTIMENT_LABELS: Record<string, string> = {
  satisfied: 'Satisfecho',
  neutral: 'Neutral',
  concerned: 'Preocupado',
  frustrated: 'Frustrado',
  angry: 'Molesto',
};

export const STATUS_LABELS: Record<string, string> = {
  idle: 'Disponible',
  understanding: 'Analizando',
  responding: 'Respondiendo',
  action_required: 'Requiere acción',
  resolved: 'Resuelto',
  escalation: 'Escalamiento',
};
