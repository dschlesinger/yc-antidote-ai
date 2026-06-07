# Antidote AI — Setup Guide

## Prerequisites
- Node.js 20+
- Python 3.11+
- `pip` or `uv`

## External services (all require accounts)
| Service | Purpose | Docs |
|---|---|---|
| LiveKit Cloud | Audio streaming, agent orchestration, **and STT + TTS via Inference** | https://cloud.livekit.io |
| Minimax | LLM (OpenAI-compatible) — `MINIMAX_MODEL` defaults to `M3.0` | https://api.minimax.chat |
| Supabase | Auth | https://supabase.com |
| Moss | Semantic search / RAG | https://moss.dev |
| Unsiloed | Document parsing | https://unsiloed.ai |

> STT (Deepgram nova-3) and TTS (Cartesia sonic-3) run via **LiveKit Inference**, billed through your LiveKit API key — no separate Deepgram or Cartesia accounts needed.

---

## 1. Clone & environment files

```bash
# Frontend
cp frontend/.env.example frontend/.env
# Fill in PUBLIC_SUPABASE_URL and PUBLIC_SUPABASE_ANON_KEY

# Backend
cp backend/.env.example backend/.env
# Fill in all credentials (LiveKit, Minimax, Supabase, Moss, Unsiloed)
```

---

## 2. Supabase setup

1. Create a new project at https://supabase.com
2. Enable Email auth under Authentication → Providers
3. Copy **Project URL** → `PUBLIC_SUPABASE_URL` / `SUPABASE_URL`
4. Copy **anon key** → `PUBLIC_SUPABASE_ANON_KEY` / `SUPABASE_ANON_KEY`
5. Copy **service_role key** → `SUPABASE_SERVICE_ROLE_KEY`

---

## 3. Moss setup

1. Create a project at https://moss.dev
2. Copy **Project ID** → `MOSS_PROJECT_ID`
3. Copy **Project Key** → `MOSS_PROJECT_KEY`
4. Create an index named `antidote-due-diligence` (the backend will call `load_index` on startup; create it first via the Moss dashboard or the backend's first document upload will bootstrap it)

---

## 4. LiveKit Cloud setup

1. Create a project at https://cloud.livekit.io
2. Copy **API Key** → `LIVEKIT_API_KEY`
3. Copy **API Secret** → `LIVEKIT_API_SECRET`
4. Copy **WebSocket URL** (e.g. `wss://your-project.livekit.cloud`) → `LIVEKIT_URL`

---

## 5. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

---

## 6. Backend (API server)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

---

## 7. Backend (LiveKit agent worker)

The agent is a separate long-running worker that registers with LiveKit Cloud and accepts job dispatches whenever a session room is created. Run it in its own terminal:

```bash
cd backend
source .venv/bin/activate
python -m app.services.agent dev    # dev mode: hot-reload + verbose logs
# or: python -m app.services.agent start  # production
```

Confirm it logs `registered worker` with your LiveKit project URL.

## 8. Run the tests

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/pytest
```

### Smoke-test the agent without a browser

`backend/scripts/smoke_test_agent.py` joins a LiveKit room as a dummy participant, publishes a WAV file as if it were the user's mic, and prints any data messages the agent sends back. Use it to verify the agent end-to-end without opening a browser tab.

```bash
# Generate a WAV (any 16-bit PCM file works; 24kHz mono is fine)
python -c "from openai import OpenAI; OpenAI().audio.speech.create(model='tts-1', voice='nova', input='Acme had revenue of twelve billion in 2025.', response_format='wav').stream_to_file('/tmp/claim.wav')"

# With the agent worker running, in another terminal:
cd backend
.venv/bin/python scripts/smoke_test_agent.py my-test-room /tmp/claim.wav
```

Look for a `DATA from agent-...` line with the interjection JSON.

---

## 9. MCP configuration (for Claude Code)

The `.mcp.json` at the repo root configures MCP servers for Supabase, LiveKit docs, and Moss. Update the placeholder values:

```json
{
  "mcpServers": {
    "supabase": { "args": ["...", "--access-token", "<your-supabase-pat>"] },
    "moss": { "env": { "MOSS_PROJECT_ID": "...", "MOSS_PROJECT_KEY": "..." } }
  }
}
```

---

## Linting

```bash
cd backend && .venv/bin/ruff check .
cd frontend && npm run check
```
