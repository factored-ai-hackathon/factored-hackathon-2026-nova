import Markdown, { type Components } from 'react-markdown';
import type { MessageRole } from '../../types';

// Agent replies come from the LLM as Markdown. react-markdown does not render raw HTML,
// so model output cannot inject markup. User and system messages stay plain text.
const components: Components = {
  a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
};

export function MessageContent({ role, content }: { role: MessageRole; content: string }) {
  if (role !== 'agent' && role !== 'human') return <>{content}</>;
  return (
    <div className="msg-markdown">
      <Markdown components={components}>{content}</Markdown>
    </div>
  );
}
