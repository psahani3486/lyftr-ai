import { useState, useRef, useEffect, useCallback } from 'react';
import ChatMessage from './components/ChatMessage.jsx';
import ChatInput from './components/ChatInput.jsx';
import SystemPrompt from './components/SystemPrompt.jsx';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function generateSessionId() {
  return 's-' + Math.random().toString(16).slice(2, 10);
}

export default function App() {
  const [sessionId] = useState(generateSessionId);
  const [messages, setMessages] = useState([]);
  const [systemPrompt, setSystemPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, scrollToBottom]);

  const sendMessage = async (text) => {
    const userMessage = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    try {
      const body = {
        session_id: sessionId,
        message: text,
      };
      if (systemPrompt.trim()) {
        body.system_prompt = systemPrompt.trim();
      }

      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        let errorDetail = `Error: ${response.status} ${response.statusText}`;
        try {
          const errorData = await response.json();
          if (errorData.detail) {
            errorDetail = typeof errorData.detail === 'string'
              ? errorData.detail
              : JSON.stringify(errorData.detail);
          }
        } catch {
          // use default error message
        }
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: errorDetail, isError: true },
        ]);
        return;
      }

      const data = await response.json();
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.reply,
          metadata: data.metadata,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Network error: ${err.message}`,
          isError: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>💬 LLM Chatbot</h1>
        <span className="session-badge">Session: {sessionId}</span>
      </header>

      <SystemPrompt value={systemPrompt} onChange={setSystemPrompt} />

      <main className="chat-container">
        <div className="messages-list">
          {messages.length === 0 && !loading && (
            <div className="empty-state">
              <p>Start a conversation by typing a message below.</p>
            </div>
          )}
          {messages.map((msg, index) => (
            <ChatMessage key={index} message={msg} />
          ))}
          {loading && (
            <div className="message-row assistant">
              <div className="message-bubble assistant loading-bubble">
                <div className="typing-indicator">
                  <span></span><span></span><span></span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </main>

      <ChatInput onSend={sendMessage} disabled={loading} />
    </div>
  );
}
