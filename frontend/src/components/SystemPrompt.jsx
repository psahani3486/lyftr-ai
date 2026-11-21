import { useState } from 'react';

export default function SystemPrompt({ value, onChange }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="system-prompt-wrapper">
      <button
        className="system-prompt-toggle"
        onClick={() => setExpanded((prev) => !prev)}
        type="button"
      >
        {expanded ? '▾' : '▸'} System Prompt
      </button>
      {expanded && (
        <div className="system-prompt-field">
          <textarea
            data-testid="system-prompt-input"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Set a system prompt for this session…"
            rows={3}
          />
        </div>
      )}
    </div>
  );
}
