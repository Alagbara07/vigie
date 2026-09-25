# VIGIE

L'intelligence qui veille sur votre entreprise.

## What is VIGIE?

VIGIE is an AI business radar for WhatsApp-first small businesses. It turns conversations into commitments, notices when those commitments are missed, and recommends the next step. A person approves that step. VIGIE does not send the message.

## Problem

A business receives messages all day. Payment promises, price questions, and ordinary greetings arrive in the same thread. The important ones get buried, and a missed payment is often noticed too late.

## Solution

VIGIE interprets each message into structured business state, evaluates that state over time, surfaces the few signals that matter, and recommends an action. The owner reviews the evidence and decides. Approval records the decision. It does not contact the customer.

## Architecture

```text
Messages
   ↓
AI Provider
   ↓
Structured Proposal
   ↓
Validation
   ↓
Domain Engine
   ↓
Events / Commitments
   ↓
Evaluation
   ↓
Signals
   ↓
Actions
   ↓
Human Approval
```

The browser talks only to Next.js. Next.js rewrites `/api/*` to FastAPI. FastAPI is the only process that connects to PostgreSQL.

```text
Next.js  →  FastAPI  →  PostgreSQL
```

There is no queue, worker, or vector database. That is deliberate. The domain model can later sit behind a queue without changing what an event, commitment, signal, or action means.

## AI architecture

Two providers implement the same interface:

* `heuristic` is deterministic and needs no credentials. It is the local default.
* `nvidia` calls a NVIDIA chat endpoint configured by environment variables.

Both return a `MessageAnalysisProposal`. Pydantic rejects a malformed proposal. The domain engine then decides what may be stored. A payment claim is never a verified payment. A promise stays pending until evaluation, using the business timezone, marks it missed. The model does not open signals, create actions, or send messages. If NVIDIA is selected and the call fails, VIGIE reports the failure. It does not silently switch to the heuristic.

`GET /api/system/ai-provider` reports the selected provider and whether it is configured. It does not return credentials.

## Demo

The local story is Adaeze Wears, timezone `Africa/Lagos`.

| Customer | Message | Result |
| --- | --- | --- |
| Amaka Bello | I'll pay the remaining ₦150,000 on Friday. | Payment commitment. Pending until the due day has passed, then missed. |
| Ngozi Eze | How much is the wholesale price for 100 units? | Unanswered request. A signal opens after the reply threshold. |
| Chinedu Okafor | I sent the ₦150,000 balance yesterday. Please confirm. | Payment claim. `payment_verified` stays false. |
| Tunde Adeyemi | Good morning. | No event, commitment, or signal. |

With `VIGIE_DEMO_MODE=true`, `POST /api/demo/run` resets that inbox and replays the story. Analysis uses `2026-09-24T09:00:00+01:00`. Evaluation then uses `2026-09-26T09:00:00+01:00`. Those are reference times, not the machine clock. The follow-up action is left `PROPOSED` so a person can approve it in the Command Center. When demo mode is off, the reset and run routes respond `404`.

Open the Command Center at [http://localhost:3000](http://localhost:3000).

## Running locally

Copy the environment file once:

```powershell
Copy-Item .env.example .env
```

Start PostgreSQL:

```powershell
docker compose up -d postgres
```

Create the API environment and start FastAPI from `apps/api`:

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start Next.js from `apps/web`:

```powershell
cd apps/web
npm install
npm run dev
```

The seeded inbox can also be loaded without the demo route:

```powershell
cd apps/api
.\.venv\Scripts\python -m app.seed
```

## Tests

From `apps/api`, with PostgreSQL running:

```powershell
.\.venv\Scripts\python -m pytest
```

From `apps/web`:

```powershell
npm test
npm run lint
npm run build
```

Backend tests use `TEST_DATABASE_URL` and the `vigie_test` database. They do not call NVIDIA. SQLite is not used.

`GET /api/health` returns `200` when the API and PostgreSQL are both reachable. If PostgreSQL is down, the same route returns `503` with `"database": "unavailable"`.

## Environment variables

Configuration lives in `.env` at the repository root. `.env` is gitignored. `.env.example` lists every variable and contains no real credentials.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `POSTGRES_USER` | Docker Compose | Database role. Development default: `vigie`. |
| `POSTGRES_PASSWORD` | Docker Compose | Database password. Development default: `vigie`. |
| `POSTGRES_DB` | Docker Compose | Development database name. Default: `vigie`. |
| `POSTGRES_PORT` | Docker Compose | Host port. Default `5433`, so a local PostgreSQL on `5432` is left alone. |
| `DATABASE_URL` | FastAPI | SQLAlchemy URL. Use `localhost` when the API runs on the host. |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | FastAPI | Database connection timeout. Default: `3`. |
| `TEST_DATABASE_URL` | pytest | PostgreSQL URL for tests. Default database: `vigie_test`. |
| `API_HOST` | FastAPI | Bind address. Default: `0.0.0.0`. |
| `API_PORT` | FastAPI | API port. Default: `8000`. |
| `AI_PROVIDER` | FastAPI | `heuristic` or `nvidia`. Unknown values are rejected. |
| `NVIDIA_API_KEY` | FastAPI | Required only for NVIDIA mode. Never commit it. |
| `NVIDIA_MODEL` | FastAPI | Model name for the NVIDIA environment in use. |
| `NVIDIA_BASE_URL` | FastAPI | API root for that environment, usually ending in `/v1`. |
| `NVIDIA_TIMEOUT_SECONDS` | FastAPI | Timeout for one NVIDIA request. Default: `30`. |
| `VIGIE_DEMO_MODE` | FastAPI | `true` enables demo reset and run. Keep `false` outside a local demo. |
| `UNANSWERED_REQUEST_THRESHOLD_MINUTES` | FastAPI | How long a request can wait before a signal. Default: `60`. |
| `API_INTERNAL_URL` | Next.js server | Rewrite target for `/api/*`. The browser does not use this value. |
| `WEB_PORT` | Next.js | Documented frontend port. Default: `3000`. |

### Local heuristic mode

```text
AI_PROVIDER=heuristic
```

No NVIDIA credentials are required.

### NVIDIA mode

```text
AI_PROVIDER=nvidia
NVIDIA_API_KEY=...
NVIDIA_MODEL=...
NVIDIA_BASE_URL=...
```

`NVIDIA_MODEL` and `NVIDIA_BASE_URL` must match the NVIDIA environment you are using. A failed NVIDIA call stays a failed NVIDIA call.

The development database password is a local default. It is not a production secret.

## Services and ports

| Service | Where it runs | Port |
| --- | --- | --- |
| PostgreSQL 16 | Docker | `5433` on the host, `5432` inside the container |
| FastAPI | Host | `8000` |
| Next.js | Host | `3000` |
