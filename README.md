# LLM Chatbot with Key Failover and Response Caching

A full-stack AI chatbot application with automatic API key failover, response caching, and multi-turn conversation support.

## 1. Live URLs

- **Frontend**: _[To be updated after deployment]_
- **Backend**: _[To be updated after deployment]_

## 2. Run Locally

### With Docker (Recommended)

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd <repo-name>
   ```

2. Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` and add your API keys:
   ```
   LLM_API_KEYS=your-gemini-key-1,your-gemini-key-2
   ```

4. Start the stack:
   ```bash
   make up
   ```

5. Open the app:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - Health check: http://localhost:8000/health

6. Stop the stack:
   ```bash
   make down
   ```

### Without Docker

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set environment variables
export LLM_API_KEYS="key1,key2"
export DATABASE_URL="sqlite:///app.db"
export ALLOWED_ORIGINS="http://localhost:3000"
export ENABLE_FAILURE_SIMULATION="true"

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:**
```bash
cd frontend
npm install

# Set environment variables
export VITE_API_URL="http://localhost:8000"

npm run dev
```

## 3. Design Decisions

### Key Fallback
- API keys are loaded from `LLM_API_KEYS` environment variable as a comma-separated list.
- Keys are assigned sequential IDs: `key_1`, `key_2`, etc.
- When a key fails with HTTP 429 (rate limit), quota error, or 5xx (server error), the system automatically tries the next key in the pool.
- The `X-Simulate-Failure` header allows testing failover without exhausting real keys (enabled via `ENABLE_FAILURE_SIMULATION=true`).
- If all keys fail, the API returns HTTP 503 with `{"detail": "all providers unavailable"}`.

### Caching
- LiteLLM's built-in in-memory cache is enabled.
- Cache key is based on the model + full message list (system prompt + history + new message).
- Cache hits return `resolution_source: "LLM_CACHE"` with identical reply text and stored token usage.
- Cache hits are significantly faster than live calls since no LLM API request is made.
- On cache hits, `key_id` is `null` and `fallback_attempts` is `0`.

### SQLite Session Storage
- All conversation history is stored in SQLite (no external services).
- The database file is persisted via Docker volume at `/data/app.db`.
- Schema is created automatically on startup.
- Each message stores session_id, role, content, metadata (JSON), and created_at (ISO-8601).
- History is loaded from SQLite for each request to maintain multi-turn context.

## 4. Verification

### Failover
Test failover using the `X-Simulate-Failure` header:

```bash
# Force key_1 to fail with 429, should fallback to key_2
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: key_1=429" \
  -d '{"session_id": "test-1", "message": "Hello"}'
# Response should show key_id: "key_2", fallback_attempts: 1

# Force all keys to fail
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: *=429" \
  -d '{"session_id": "test-2", "message": "Hello"}'
# Response should be 503 with {"detail": "all providers unavailable"}
```

### Cache Hits
1. Send a message: `{"session_id": "s-abc1", "message": "What is 2+2?"}`
2. Start a new session and send the same message: `{"session_id": "s-abc2", "message": "What is 2+2?"}`
3. The second response should show `resolution_source: "LLM_CACHE"` with lower latency.

### Per-message Token Usage
Each response includes `input_tokens` and `output_tokens` in the metadata. These are per-request values, not cumulative totals. The UI displays these next to each assistant message.

## 5. Setup Used

- **Editor**: VS Code with AI assistance
- **AI Tools**: Google Antigravity (Gemini), used for code generation and architecture decisions
- **Backend**: Python 3.11, FastAPI, LiteLLM, aiosqlite
- **Frontend**: React 18, Vite
- **Deployment**: Docker with multi-stage builds

## 6. Bonus Features

- **System Prompt**: Users can set a custom system prompt for their session via the UI.
- **Loading Indicator**: Visual feedback while waiting for AI responses.
- **Auto-scroll**: Chat automatically scrolls to the latest message.
- **Dark Theme**: Clean, modern dark theme UI.
- **Responsive Design**: Works on desktop and mobile screens.
