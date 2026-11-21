export default function ChatMessage({ message }) {
  const { role, content, metadata, isError } = message;

  if (role === 'user') {
    return (
      <div className="message-row user">
        <div className="message-bubble user">{content}</div>
      </div>
    );
  }

  const sourceClass = metadata?.resolution_source === 'LLM_CACHE'
    ? 'source-cache'
    : 'source-live';

  return (
    <div className="message-row assistant">
      <div
        className={`message-bubble assistant${isError ? ' error' : ''}`}
        data-testid="assistant-message"
      >
        <div>{content}</div>
        {metadata && (
          <div className="message-meta">
            <span className={`meta-chip ${sourceClass}`} data-testid="meta-source">
              <span className="meta-label">Source</span>
              {metadata.resolution_source}
            </span>
            <span className="meta-chip" data-testid="meta-model">
              <span className="meta-label">Model</span>
              {metadata.model}
            </span>
            <span className="meta-chip" data-testid="meta-latency">
              <span className="meta-label">Latency</span>
              {metadata.latency_ms} ms
            </span>
            <span className="meta-chip" data-testid="meta-input-tokens">
              <span className="meta-label">In</span>
              {metadata.input_tokens}
            </span>
            <span className="meta-chip" data-testid="meta-output-tokens">
              <span className="meta-label">Out</span>
              {metadata.output_tokens}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
