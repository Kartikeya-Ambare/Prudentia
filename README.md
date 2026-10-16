# Prudentia

Asset-allocation recommender: tell it how much, for how long and how much risk, and it splits the money across
stocks, mutual funds and fixed deposits, projects the outcome, and lets you adjust the plan by chat.

```
Prudentia/
  frontend/      React app (Vite, :5173)               the UI, Beginner chat mode and Expert form mode
  backend/       Engine API (FastAPI, :8000)           data, forecasts, optimiser, plan API
  chat-service/  Chat + guardrails (FastAPI, :8001)    talks to Ollama, calls the backend
  mascot/        Prudie, the animated mascot           used by the frontend
  docs/          colour palette
  start-all.cmd  starts backend, chat service and frontend
```

## First-time setup

Needs Python 3.11+, Node 20+ and [Ollama](https://ollama.com) with the two chat models pulled
(`qwen2.5:1.5b-instruct`, `llama3.2:1b`).

```
cd backend       && pip install -r requirements.txt
cd chat-service  && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
cd frontend      && npm install
```

## Run

Start Ollama, then run `start-all.cmd` and open http://localhost:5173.

## Test

```
cd backend       && python -m pytest -q
cd chat-service  && .venv\Scripts\python -m pytest -q
cd frontend      && npm run build
```

## Data

`backend/data/asset_allocation.db` holds prices, NAV history and fund sector tables. `backend/universe/` lists the
stocks, banks and mutual funds the app can pick from. Fund sector tables come from `backend/data/mf_portfolios/manual_sectors.json`;
after editing it run, from `backend/`:

```
python -I scripts/build_mf_sector_snapshot.py
python scripts/load_mf_sector_snapshot.py
```

`python download.py` (in `backend/`) refreshes prices and NAV history.
