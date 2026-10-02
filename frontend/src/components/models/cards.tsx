/** Stat tiles and chart cards shared by the /modelos sections. */
import type { ReactNode } from 'react';

export function Stat({ value, label, sub }: { value: string; label: string; sub?: string }) {
  return (
    <div className="models-stat">
      <div className="models-stat-value">{value}</div>
      <div className="models-stat-label">{label}</div>
      {sub && <div className="models-stat-sub">{sub}</div>}
    </div>
  );
}

export function Card({ title, question, children }: { title: string; question?: string; children: ReactNode }) {
  return (
    <section className="models-card">
      <header>
        <h3>{title}</h3>
        {question && <p className="models-question">{question}</p>}
      </header>
      {children}
    </section>
  );
}
