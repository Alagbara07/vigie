# VIGIE production deployment

This document prepares a deployment. It does not mean VIGIE is deployed, and it does not require `vigiehq.xyz` to be active.

The browser stays on the Vercel host. Next.js rewrites `/api/*` to `API_INTERNAL_URL` on the server. Session cookies are host-only, so signed-in requests do not call the API host directly from the browser.

## Initial hackathon deployment

Use the HTTPS URLs Vercel and Render assign. No custom domain is required.

```text
Vercel-generated HTTPS URL
        ↓
Render-generated HTTPS URL
        ↓
Neon PostgreSQL
```

After the first deploy, copy the real hosts into the environment. Replace nothing in application code.

| Variable | Where | Value for this phase |
| --- | --- | --- |
| `PUBLIC_WEB_URL` | Render | The Vercel origin, such as `https://vigie-xxxx.vercel.app` |
| `CORS_ORIGINS` | Render | Empty, unless a second frontend origin must be allowed. `PUBLIC_WEB_URL` is already allowed. |
| `API_PUBLIC_URL` | Render web service and the Gmail cron | The Render origin, such as `https://vigie-api.onrender.com` |
| `API_INTERNAL_URL` | Vercel | The same Render origin |
| `APP_ENV` | Render | `production` |
| `VIGIE_DEMO_MODE` | Render | `false` |
| `DATABASE_URL` | Render web service and the Gmail cron | The Neon connection string |
| `CREDENTIAL_ENCRYPTION_KEY` | Render web service and the Gmail cron | A Fernet key. Never commit it. |

`render.yaml` does not contain a frontend or API hostname. Render prompts for `PUBLIC_WEB_URL`, `CORS_ORIGINS`, and `API_PUBLIC_URL`.

Production refuses to start when `PUBLIC_WEB_URL` is not an HTTPS origin, when it points at localhost, or when a configured browser origin is not HTTPS. `*` is never added to CORS.

When `GOOGLE_REDIRECT_URI`, `MICROSOFT_REDIRECT_URI`, or `GMAIL_PUBSUB_AUDIENCE` is empty, the API builds them from `API_PUBLIC_URL`:

```text
{API_PUBLIC_URL}/api/integrations/gmail/callback
{API_PUBLIC_URL}/api/integrations/microsoft/callback
{API_PUBLIC_URL}/api/integrations/gmail/pubsub
{API_PUBLIC_URL}/api/integrations/whatsapp/webhook
```

Set an explicit variable only when that URL must differ from the public API origin. In production those URLs must be `https://`. An `http://` callback is treated as not configured.

### Neon

1. Create a Neon project and a PostgreSQL database.
2. Put the connection string in Render as `DATABASE_URL`. Do not commit it.
3. Neon usually gives `postgres://` or `postgresql://`. The API rewrites that to `postgresql+psycopg://`. When `APP_ENV=production` and the URL has no `sslmode`, the API adds `sslmode=require`.
4. The Render blueprint runs `alembic upgrade head` before each deploy, from `apps/api`. `alembic/env.py` reads `DATABASE_URL` from application settings.

### Render

Connect the GitHub repository yourself. Applying `render.yaml` is a dashboard step.

| Setting | Value |
| --- | --- |
| Name | `vigie-api` |
| Root directory | `apps/api` |
| Runtime | Python 3.11 (`runtime.txt`) |
| Build | `pip install .` from `apps/api`. `pip install -r requirements.txt` installs the same project because `requirements.txt` points at `pyproject.toml`. |
| Pre-deploy | `alembic upgrade head` |
| Start | `python -m app` |
| Health check | `GET /api/health` |

`python -m app` binds `0.0.0.0` and the platform `PORT`. Local development keeps `API_PORT` (default `8000`) when `PORT` is unset or `0`.

`GET /api/health` returns `200` with `status`, `service`, `api`, and `database` when PostgreSQL answers `SELECT 1`. It returns `503` when the database is unreachable. The body and the log line do not include the connection string or a stack trace.

In production the API hides `/docs`, `/redoc`, and `/openapi.json`. The process warns if demo mode is on or `CREDENTIAL_ENCRYPTION_KEY` is unset.

Gmail watches expire. Renew them with the existing command. Do not add Celery, Redis, or another queue.

```bash
python -m app.jobs.renew_gmail_watches
```

| Cron setting | Value |
| --- | --- |
| Name | `vigie-gmail-watch-renewal` |
| Schedule | `0 6 * * *` (06:00 UTC every day) |
| Command | `python -m app.jobs.renew_gmail_watches` |

Render cron jobs do not inherit the web service environment. Set `DATABASE_URL`, `API_PUBLIC_URL`, `CREDENTIAL_ENCRYPTION_KEY`, the Google OAuth variables, and the `GMAIL_PUBSUB_*` variables on the cron service. `GMAIL_WATCH_RENEW_WITHIN_HOURS` defaults to `24`.

A watch shows **Listening** only after Google accepts `users.watch` and the stored expiration is still in the future.

### Vercel

| Setting | Value |
| --- | --- |
| Root directory | `apps/web` |
| Framework | Next.js |
| `API_INTERNAL_URL` | The Render HTTPS origin |

`API_INTERNAL_URL` is read by the Next.js server. It is not a `NEXT_PUBLIC_` variable. A Vercel build fails if it is missing or points at localhost. Local `next build` still defaults to `http://127.0.0.1:8000` when `VERCEL` is not set.

Use the URL Vercel shows after the first deployment as `PUBLIC_WEB_URL` on Render. Redeploy is not required for that API setting, but restart the Render service after changing it.

### Sessions

There is no `SESSION_SECRET`, and one is not required.

Signing in creates a 256-bit random token with `secrets.token_urlsafe(32)`. The cookie stores that token. The database stores only its SHA-256 hash, plus expiry and a revocation time. Every request looks the token up by that hash. A missing, expired, or revoked row is signed out. The cookie is `HttpOnly` and `SameSite=Lax`. It is `Secure` when `APP_ENV=production` or `PUBLIC_WEB_URL` starts with `https://`.

Passwords are PBKDF2-SHA256 with a random salt and are never returned. Provider tokens use `CREDENTIAL_ENCRYPTION_KEY` (Fernet) and are a separate secret from the session.

OAuth `state` is a random single-use value bound to the user and the business.

### OAuth, WhatsApp, and Gmail

Register the derived URLs in each provider console, using the Render host from `API_PUBLIC_URL`.

Gmail OAuth redirect:

```text
{API_PUBLIC_URL}/api/integrations/gmail/callback
```

Gmail requests OpenID, email, profile, and Gmail readonly, with offline access. It does not send or modify mail. `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are required on the Render API before the card can say Ready to connect. `GOOGLE_REDIRECT_URI` can stay empty so the API derives the callback from `API_PUBLIC_URL`. Pub/Sub is required only for automatic listening. Sync now works without it. The renewal cron needs the same Google and Pub/Sub values as the API when listening is enabled.

Microsoft OAuth redirect:

```text
{API_PUBLIC_URL}/api/integrations/microsoft/callback
```

Microsoft uses delegated `User.Read`, `Mail.Read`, and `offline_access`, plus the OpenID `email` scope. `User.Read` is what lets the callback read the Outlook mailbox from Microsoft Graph. It does not send mail and it has no cron job. `MICROSOFT_TENANT_ID=common` is the authority that can accept mailboxes from more than one organization, when the Entra app is registered as multi-tenant. A directory ID restricts sign-in to that tenant.

WhatsApp webhook:

```text
{API_PUBLIC_URL}/api/integrations/whatsapp/webhook
```

Gmail Pub/Sub push URL and OIDC audience:

```text
{API_PUBLIC_URL}/api/integrations/gmail/pubsub
```

The push route still verifies the Google-signed bearer token, matches the mailbox to one business, and ignores a second delivery of the same Gmail message. The webhook route still verifies the Meta challenge and signature. Leave Meta, Google, and Microsoft credentials empty until those apps exist. The channel then stays **Not configured**.

`PUBLIC_WEB_URL` is where the API sends the browser after OAuth. It must be the Vercel origin the person is using.

## Later custom domain

`vigiehq.xyz` is optional. When DNS and certificates exist, change environment values only:

```text
PUBLIC_WEB_URL=https://app.vigiehq.xyz
CORS_ORIGINS=https://vigiehq.xyz,https://app.vigiehq.xyz
API_PUBLIC_URL=https://api.vigiehq.xyz
API_INTERNAL_URL=https://api.vigiehq.xyz
```

Point the names as follows, using the records Vercel and Render show:

| Name | Target |
| --- | --- |
| `vigiehq.xyz` | Vercel |
| `app.vigiehq.xyz` | Vercel |
| `api.vigiehq.xyz` | Render |

Redirect `https://vigiehq.xyz` to `https://app.vigiehq.xyz` so a person has one cookie host. Then update the Google, Microsoft, Meta, and Pub/Sub consoles to the new `API_PUBLIC_URL` callbacks. Clear `GOOGLE_REDIRECT_URI`, `MICROSOFT_REDIRECT_URI`, and `GMAIL_PUBSUB_AUDIENCE` if they were set to the old Render host, so the API derives the new ones.

## Security variables

Set every secret in Neon, Render, or Vercel. `.env`, `.env.local`, `.env.development`, and `.env.production` are gitignored. `.env.example` documents names only.

| Variable | Where | Notes |
| --- | --- | --- |
| `APP_ENV` | Render | `production` |
| `VIGIE_DEMO_MODE` | Render | `false` |
| `DATABASE_URL` | Render, including the cron | Neon URL. Never commit it. |
| `CREDENTIAL_ENCRYPTION_KEY` | Render, including the cron | Fernet key. Never commit it. |
| `PUBLIC_WEB_URL` | Render | HTTPS origin of the frontend actually in use |
| `CORS_ORIGINS` | Render | Extra exact HTTPS origins. Empty for a single Vercel URL. |
| `API_PUBLIC_URL` | Render, including the cron | HTTPS origin of the API actually in use |
| `AI_PROVIDER` | Render | `heuristic` until NVIDIA is intentionally enabled |
| `NVIDIA_API_KEY` | Render | Empty unless `AI_PROVIDER=nvidia` |
| `NVIDIA_MODEL` | Render | Required only for NVIDIA |
| `NVIDIA_BASE_URL` | Render | Required only for NVIDIA |
| `GOOGLE_CLIENT_ID` | Render, including the cron | Google OAuth client |
| `GOOGLE_CLIENT_SECRET` | Render, including the cron | Google OAuth secret |
| `GOOGLE_REDIRECT_URI` | Render, including the cron | Optional. Derived from `API_PUBLIC_URL` when empty. |
| `GMAIL_PUBSUB_TOPIC` | Render, including the cron | Pub/Sub topic |
| `GMAIL_PUBSUB_AUDIENCE` | Render, including the cron | Optional. Derived from `API_PUBLIC_URL` when empty. |
| `GMAIL_PUBSUB_SERVICE_ACCOUNT` | Render, including the cron | Push service account |
| `GMAIL_WATCH_RENEW_WITHIN_HOURS` | Render cron | Optional. Default `24` |
| `MICROSOFT_CLIENT_ID` | Render | Microsoft app id |
| `MICROSOFT_CLIENT_SECRET` | Render | Microsoft secret |
| `MICROSOFT_TENANT_ID` | Render | Usually `common` |
| `MICROSOFT_REDIRECT_URI` | Render | Optional. Derived from `API_PUBLIC_URL` when empty. |
| `META_APP_ID` | Render | Meta app |
| `META_APP_SECRET` | Render | Webhook signature |
| `META_VERIFY_TOKEN` | Render | Webhook challenge |
| `META_ACCESS_TOKEN` | Render | WhatsApp access |
| `META_WHATSAPP_BUSINESS_ACCOUNT_ID` | Render | Optional until a number is connected in the product |
| `META_PHONE_NUMBER_ID` | Render | Optional until a number is connected in the product |
| `API_INTERNAL_URL` | Vercel | Same origin as `API_PUBLIC_URL` |

Logs record business id, provider, external message id, and error category. They do not record OAuth tokens, passwords, encryption keys, authorization headers, or message bodies. Unhandled API errors return `Internal server error` without a stack trace.
