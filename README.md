# VIGIE

L'intelligence qui veille sur votre entreprise.

VIGIE is an AI-powered business radar for WhatsApp-first small and medium businesses. It turns unstructured business conversations into events, signals, and recommended actions that a person approves before anything is executed.

Your business is talking all day. VIGIE tells you what matters.

## Architecture

```text
Next.js  →  FastAPI  →  PostgreSQL
```

The browser talks only to Next.js. Requests to `/api/*` are rewritten by the Next.js server to FastAPI. FastAPI is the only process that connects to PostgreSQL.

The domain tables for businesses, conversations, events, commitments, signals, and actions are in PostgreSQL. A message is analyzed like this:

```text
Message → Provider → Proposal → Validation → Domain logic
```

The provider may be the local heuristic or NVIDIA. Both return the same proposal. Validation and the domain engine decide what is stored. The model does not verify payments, open signals, or send messages. `POST /api/evaluations/run` turns persisted commitments and request events into signals. `POST /api/actions/recommend` turns an open signal into one recommendation. Approving or rejecting that recommendation records the decision and does not send a message. The Command Center at `/` reads `GET /api/dashboard/summary` and the signal APIs. `GET /api/system/ai-provider` reports which provider is selected, without credentials.

## Local development

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
.\.venv\Scripts\uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Start Next.js from `apps/web`:

```powershell
cd apps/web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The page reads system status from `/api/health` on the Next.js origin. Next.js forwards that request to FastAPI.

Apply migrations and load the demo inbox from `apps/api`:

```powershell
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\python -m app.seed
```

Run the API tests from `apps/api` while PostgreSQL is running. Pytest applies the same migrations to `vigie_test`.

```powershell
.\.venv\Scripts\python -m pytest
```

Build the frontend from `apps/web`:

```powershell
npm run build
```

## Environment variables

Configuration lives in `.env` at the repository root. `.env.example` lists every variable. Do not commit `.env`.

| Variable | Used by | Purpose |
| --- | --- | --- |
| `POSTGRES_USER` | Docker Compose | Database role. Development default: `vigie`. |
| `POSTGRES_PASSWORD` | Docker Compose | Database password. Development default: `vigie`. |
| `POSTGRES_DB` | Docker Compose | Development database name. Default: `vigie`. |
| `POSTGRES_PORT` | Docker Compose | Host port published for PostgreSQL. Default: `5433`, so a local PostgreSQL on `5432` does not intercept connections. |
| `DATABASE_URL` | FastAPI | SQLAlchemy URL. Use `localhost` when the API runs on the host. |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | FastAPI | How long a database connection attempt may wait. Default: `3`. |
| `TEST_DATABASE_URL` | pytest | PostgreSQL URL for tests. Default database: `vigie_test`. |
| `API_HOST` | FastAPI | Bind address. Default: `0.0.0.0`. |
| `API_PORT` | FastAPI | API port. Default: `8000`. |
| `AI_PROVIDER` | FastAPI | `heuristic` or `nvidia`. An unknown value is rejected. NVIDIA does not fall back to the heuristic. |
| `NVIDIA_API_KEY` | FastAPI | Required only when `AI_PROVIDER=nvidia`. Never commit this value. |
| `NVIDIA_MODEL` | FastAPI | Model name expected by the NVIDIA environment. Required for NVIDIA mode. |
| `NVIDIA_BASE_URL` | FastAPI | API root for that environment, usually ending in `/v1`. Required for NVIDIA mode. |
| `NVIDIA_TIMEOUT_SECONDS` | FastAPI | HTTP timeout for one NVIDIA request. Default: `30`. |
| `UNANSWERED_REQUEST_THRESHOLD_MINUTES` | FastAPI | How long a stored request can wait without a business reply before evaluation opens a signal. Default: `60`. |
| `API_INTERNAL_URL` | Next.js server | Rewrite target for `/api/*`. The browser does not use this value. |
| `WEB_PORT` | Next.js | Documented frontend port. Default: `3000`. |

### Local heuristic mode

```text
AI_PROVIDER=heuristic
```

No NVIDIA credentials are required. This is the default. The heuristic provider is deterministic and stays available when NVIDIA is not selected.

### NVIDIA mode

```text
AI_PROVIDER=nvidia
NVIDIA_API_KEY=...
NVIDIA_MODEL=...
NVIDIA_BASE_URL=...
```

`NVIDIA_MODEL` and `NVIDIA_BASE_URL` must match the NVIDIA environment you are using. `NVIDIA_BASE_URL` is the API root, usually ending in `/v1`. VIGIE sends a chat completion there and validates the JSON before anything is stored. If NVIDIA is selected and a request fails, VIGIE reports that failure. It does not silently switch to the heuristic.

`apps/web` loads the root `.env` when Next.js starts, so `API_INTERNAL_URL` does not need a second file.

The development password is a local default. It is not a production secret.

## Services and ports

| Service | Where it runs | Port |
| --- | --- | --- |
| PostgreSQL 16 | Docker | `5433` on the host, `5432` inside the container |
| FastAPI | Host | `8000` |
| Next.js | Host | `3000` |

PostgreSQL is on a Compose network and its port is published to the host so FastAPI can connect with `localhost`. A future API container would use the hostname `postgres` instead.

## Tests

Backend tests run against PostgreSQL. They use `TEST_DATABASE_URL`, which points at `vigie_test`. That database is created the first time the Docker volume is initialized. SQLite is not used.

`GET /api/health` returns `200` when the API and PostgreSQL are both reachable:

```json
{
  "status": "ok",
  "service": "vigie-api",
  "api": "ok",
  "database": "ok"
}
```

If PostgreSQL is down, the same route returns `503` with `"database": "unavailable"`. The API process is still up. If the Next.js page cannot reach FastAPI at all, the page shows that the API is unavailable.
