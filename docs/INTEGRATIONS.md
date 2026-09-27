# How channels connect to VIGIE

VIGIE is a channel-agnostic intelligence layer. A provider adapter verifies the provider, identifies the business, and turns the payload into one normalized message. Ingestion stores that message once. The existing analysis service interprets it. The engine does not contain WhatsApp, Gmail, or Microsoft branches.

The application does not require a GPU, and it does not depend on any NVIDIA hosting product. The heuristic provider runs with no external credentials. NVIDIA, when configured, is only an AI provider behind the same interface.

## Architecture

```text
WhatsApp / Gmail / Microsoft 365 / Demo
        ↓
Provider adapter
        ↓
Normalized message
        ↓
Ingestion
        ↓
schedule_message_analysis()
        ↓
Existing VIGIE pipeline
```

`schedule_message_analysis()` is the boundary a queue can replace later. Adapters do not create signals, commitments, or recommendations themselves.

## Implemented

* Demo connector, labeled Prototype. It is available only when `VIGIE_DEMO_MODE=true`.
* WhatsApp Cloud API webhook verification and `X-Hub-Signature-256` checks.
* Routing an inbound WhatsApp message to the business that connected that phone number ID.
* Gmail and Microsoft OAuth connect and callback, with a single-use server-side `state`.
* Normalization of Gmail API and Microsoft Graph message resources.
* A pull sync for a connected mailbox. It calls the provider API. It does not scrape.
* Connection status that stays "Not configured" until credentials exist, and "Connected" only after a connection is stored.
* Idempotency on `business_id + source + external_message_id`.
* Approval still records a decision and does not send a customer message. `send_message()` refuses.

## Requires external provider configuration

These are not claimed as live connections in this repository:

* A Meta app, WhatsApp Business account, permanent token, and a public HTTPS webhook URL.
* Meta app review if the app will be used by other businesses.
* A Google Cloud OAuth client, the Gmail readonly scope, and the redirect URI below.
* A Google Cloud Pub/Sub topic, a push subscription, and a public HTTPS endpoint before Gmail can listen. Until those exist, Gmail stays on manual sync.
* A Microsoft app registration, tenant, `Mail.Read`, and the redirect URI below.
* `CREDENTIAL_ENCRYPTION_KEY` in the API environment. OAuth tokens are encrypted before they are written to `integration_credentials`. The key is not stored in the database. Plaintext tokens are not returned by the API and are not written to logs.

## WhatsApp setup

Set the Meta variables in the environment. Do not commit them.

```text
META_APP_ID
META_APP_SECRET
META_VERIFY_TOKEN
META_ACCESS_TOKEN
META_WHATSAPP_BUSINESS_ACCOUNT_ID
META_PHONE_NUMBER_ID
```

`META_APP_SECRET`, `META_VERIFY_TOKEN`, and `META_ACCESS_TOKEN` must all be present before a business can connect. The phone number ID is stored on that business's connection and is how a webhook chooses the tenant.

Callback and webhook URL:

```text
https://<your-api>/api/integrations/whatsapp/webhook
```

Meta's verification request is `GET` with `hub.mode`, `hub.verify_token`, and `hub.challenge`. VIGIE returns the challenge only when the verify token matches. `POST` deliveries must carry `X-Hub-Signature-256` computed with the app secret. A bad signature is rejected. An unknown phone number is ignored. A repeated Meta message ID returns the stored message and does not analyze it again.

VIGIE does not ask for a WhatsApp password.

## Gmail OAuth

```text
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
```

Redirect URI:

```text
https://<your-api>/api/integrations/gmail/callback
```

The requested scope is `https://www.googleapis.com/auth/gmail.readonly`. The browser is sent to Google. The callback reads `state` from the server-side record and does not trust a `business_id` on the callback. Tokens stay on the server. `POST /api/integrations/gmail/sync` reads recent messages through the Gmail API.

## Gmail real-time setup

OAuth and Pub/Sub are separate. The API starts, the demo runs, and Gmail shows "Not configured" when the Google values are empty. Manual sync remains available after OAuth even if Pub/Sub is not configured. "Listening" is shown only after Gmail accepts a watch.

This repository has not been tested against a live Google Cloud project.

1. Create a Google Cloud project and enable the Gmail API.
2. Create an OAuth client. Set the redirect URI to `https://<your-api>/api/integrations/gmail/callback`. The scope is `https://www.googleapis.com/auth/gmail.readonly`.
3. Put `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` in the API environment. Do not commit them.
4. Create a Pub/Sub topic, for example `projects/PROJECT_ID/topics/vigie-gmail`. Grant `gmail-api-push@system.gserviceaccount.com` the Pub/Sub Publisher role on that topic. Gmail's watch call publishes there.
5. Create a push subscription on that topic. The push endpoint is `https://<your-api>/api/integrations/gmail/pubsub`. Enable authentication and set the audience to that same URL. Note the push service account email.
6. Set `GMAIL_PUBSUB_TOPIC`, `GMAIL_PUBSUB_AUDIENCE`, and `GMAIL_PUBSUB_SERVICE_ACCOUNT`. The audience is the push URL. The service account is the identity Google puts on the push token.
7. After a business connects Gmail, VIGIE reads the current history id, syncs recent mail, calls `users.watch`, then reads history since that baseline so mail that arrives during registration is not skipped. The watch response's expiration is stored as Google returns it.
8. `POST /api/integrations/gmail/pubsub` accepts the push. It verifies the Google OIDC bearer token, checks that the subscription belongs to the same project as the topic, and only then reads `emailAddress` and `historyId`. The notification is not the email. VIGIE calls `history.list` and fetches the changed messages. An unknown mailbox is acknowledged and ignored. A repeated delivery does not create another message, event, commitment, or signal.
9. The endpoint requires HTTPS in production. Google will not push to a laptop address. Locally, use Connect and Sync now. Real-time listening stays "Not configured" until the three Pub/Sub variables are set.
10. Watches expire. Renew them before the stored expiration. Run `python -m app.jobs.renew_gmail_watches` once a day from the host scheduler. The command uses the expiration Google returned and `GMAIL_WATCH_RENEW_WITHIN_HOURS` (default 24). It does not assume a fixed watch lifetime. No queue or cache is required.
11. If Gmail says the stored history id is gone, VIGIE syncs recent messages and stores a new history baseline. A failed watch leaves the mailbox connected, records the error, and can be retried with Enable real-time listening.

## Microsoft OAuth

```text
MICROSOFT_CLIENT_ID
MICROSOFT_CLIENT_SECRET
MICROSOFT_TENANT_ID
MICROSOFT_REDIRECT_URI
```

Redirect URI:

```text
https://<your-api>/api/integrations/microsoft/callback
```

The requested scope is `offline_access` and `https://graph.microsoft.com/Mail.Read`. `MICROSOFT_TENANT_ID` can be `common` for multi-tenant sign-in, or a directory ID. `POST /api/integrations/microsoft/sync` reads recent Outlook messages through Microsoft Graph.

## Environment variables

See `.env.example`. Empty provider values are valid. The API starts, the demo connector still works when demo mode is on, and real providers show "Not configured".

`PUBLIC_WEB_URL` is where OAuth sends the browser afterward. It is not a secret.

## Local development

1. Start PostgreSQL and the API without provider credentials.
2. Open `/settings/integrations`.
3. Use Demo WhatsApp to send a message through the normal pipeline.
4. Add provider credentials only when the external app exists. Restart the API so it reads them. The status becomes "Available", then "Connected" after the business finishes the provider flow.

## Production

Run the API, the web app, and PostgreSQL on ordinary cloud infrastructure. Put the API behind HTTPS so Meta, Google, and Microsoft can call it. Keep provider secrets in the host's secret store. Do not log tokens, authorization headers, or message bodies.

A queue is not required. `schedule_message_analysis()` is the place to move interpretation off the webhook later.

## Security

* Webhook signatures and OAuth `state` are checked before a message or connection is stored.
* OAuth `state` is random, expires, and cannot be reused. It is bound to the user, business, and provider that started the connection. The callback does not accept a business id from the query string.
* One connected phone number, mailbox, or Microsoft account maps to one business. Another business cannot claim it.
* API responses and credential `repr` omit access tokens and refresh tokens.
* Provider passwords are never collected.
* Business data routes require a signed-in member of that business. A `business_id` in the request is checked against that membership. Provider webhooks still use provider verification rather than a user session.
* Demo reset, demo run, and the demo connector are available only when `VIGIE_DEMO_MODE=true`, and only to a member of the demo business. Leave demo mode off outside a local demonstration.

## Idempotency

`business_id`, `source`, and `external_message_id` uniquely identify an imported message. Provider retries return the existing row and do not create another event, commitment, signal, or recommendation.

## Tenant isolation

Every connection and message belongs to one business. WhatsApp routing uses the connected phone number ID. Mail sync uses the token stored for that business's connection. A message stored for one business is not visible to another.

## Future connectors

A new channel implements the provider adapter: validate credentials, report status, normalize a payload, and refuse outbound sending until a human approval path explicitly calls it. It should emit a `NormalizedMessage` and stop. Analysis, evaluation, and approval stay shared.

## NVIDIA provider

`AI_PROVIDER=heuristic` is the default and needs no key. `AI_PROVIDER=nvidia` uses `NVIDIA_API_KEY`, `NVIDIA_MODEL`, and `NVIDIA_BASE_URL` as an HTTP AI provider. Those settings do not change how messages are ingested. If NVIDIA is selected and the call fails, VIGIE reports the failure and does not silently switch to the heuristic.
