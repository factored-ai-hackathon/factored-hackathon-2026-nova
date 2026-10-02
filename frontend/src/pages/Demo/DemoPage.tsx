/**
 * DemoPage — the entry point for visitors and judges, at the bare host name (/demo redirects
 * here): the three parts of the demo, each with one line on what it is and its published demo
 * key. All data is synthetic.
 */
import { Link } from 'react-router-dom';
import { ArrowRight, Headset, LineChart, MessageCircle } from 'lucide-react';
import '../../styles/demo.css';

const ENTRIES = [
  {
    to: '/login',
    icon: MessageCircle,
    title: 'Customer app',
    what: 'Log in as a synthetic bank customer and ask Nova, the AI agent, about your accounts in Spanish or Portuguese.',
    key: 'Open "Modo demo" on the login page · password Nova2026 · the SMS code is shown on screen',
  },
  {
    to: '/console',
    icon: Headset,
    title: 'Human agent console',
    what: 'Where the cases Nova hands over arrive, with the verified facts, the evidence and how faithful each answer was to the data.',
    key: 'Key Asesor2026 (shown in the field)',
  },
  {
    to: '/models',
    icon: LineChart,
    title: 'Do the models work?',
    what: 'How the intent classifier and the knowledge search are measured, the cost per token and live numbers from production.',
    key: 'Password Modelos2026 (shown in the field)',
  },
] as const;

export function DemoPage() {
  return (
    <div className="demo-hub">
      <header className="demo-hub-head">
        <p className="demo-hub-eyebrow">Factored AI &amp; Data Hackathon 2026</p>
        <h1>Nova</h1>
        <p>
          An AI agent for a bank's contact center: it solves declined-payment and complaint questions on the first
          contact, and hands the rest to a person with the facts. Pick where to start.
        </p>
      </header>
      <nav className="demo-hub-cards" aria-label="Demo">
        {ENTRIES.map(({ to, icon: Icon, title, what, key }) => (
          <Link key={to} to={to} className="demo-hub-card" aria-labelledby={`demo-${to.slice(1)}`}>
            <Icon size={28} aria-hidden="true" />
            <h2 id={`demo-${to.slice(1)}`}>{title}</h2>
            <p className="demo-hub-what">{what}</p>
            <p className="demo-hub-key">{key}</p>
            <span className="demo-hub-go">
              {to} <ArrowRight size={16} aria-hidden="true" />
            </span>
          </Link>
        ))}
      </nav>
      <p className="demo-hub-note">All customers and data are synthetic: the challenge's dataset, no real people.</p>
    </div>
  );
}
