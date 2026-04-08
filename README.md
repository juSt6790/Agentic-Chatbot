# projectChat

Personal workspace: **Flask agent backend** (`agent_backend/`) plus a **React + Vite** chat UI (`frontend/`).

## Layout

| Path | What |
|------|------|
| `agent_backend/` | Flask app, `python3 app.py` (port 8000 by default) |
| `frontend/` | Chat UI → `POST /chat` on the backend |
| `.venv/` | Python venv (local only, not in git) |

## Quick start

**Backend** (from repo root):

```bash
source .venv/bin/activate   # or your venv
cd agent_backend && python3 app.py
```

**Frontend**:

```bash
cd frontend && npm install && npm run dev
```

Configure the Bearer token in the UI (Connect). For dev, Vite proxies `/chat` to `http://127.0.0.1:8000`.

## Env

Copy `agent_backend/.env.example` when you add one — real `.env` files stay on your machine only.

---

*Private / personal project.*
