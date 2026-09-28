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
{API_PUBLIC_URL}/api/integrations/whatsapp/webhook
```

The integrations page shows that URL when `API_PUBLIC_URL` is set. It does not show the app secret, verify token, or access token. Register the callback in Meta and subscribe to messages there. VIGIE does not do that step. A phone number shows Connected only after this business saves that phone number ID. Incoming text is then routed by that ID. Approval still does not send a WhatsApp message.

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
{API_PUBLIC_URL}/api/integrations/gmail/callback
```

Leave `GOOGLE_REDIRECT_URI` empty and set `API_PUBLIC_URL` to the public API origin. The API then uses that redirect. Set `GOOGLE_REDIRECT_URI` only when the callback must differ from that derived URL. Production rejects an HTTP or localhost redirect.

VIGIE requests `openid`, `email`, `profile`, and `https://www.googleapis.com/auth/gmail.readonly`, with offline access so the access token can be refreshed. It does not request Gmail send, modify, or delete. The browser is sent to Google. The callback reads `state` from the server-side record and does not trust a `business_id` on the callback. Tokens stay on the server. `POST /api/integrations/gmail/sync` reads recent messages through the Gmail API and passes them through the same message pipeline as the other channels. VIGIE does not send email.

A connected mailbox shows as Connected, with the stored Gmail address. Sync now imports recent mail. Disconnect removes the stored mailbox, tokens, and watch routing, so a later sync or notification does not import mail. If the refresh token is missing or rejected, the channel needs attention and the mailbox must be connected again. An expired access token is refreshed before sync. An expired Gmail watch is renewed by the daily command when Pub/Sub is configured; until then the card stays connected and Sync now remains the way to import mail. Listening is shown only while the stored watch expiration is still in the future.

## Gmail real-time setup

OAuth and Pub/Sub are separate. The API starts, the demo runs, and Gmail shows "Not configured" when the Google values are empty. Manual sync remains available after OAuth even if Pub/Sub is not configured. "Listening" is shown only after Gmail accepts a watch.

This repository has not been tested against a live Google Cloud project.

1. Create a Google Cloud project and enable the Gmail API.
2. Create an OAuth client. The redirect URI is `{API_PUBLIC_URL}/api/integrations/gmail/callback` unless `GOOGLE_REDIRECT_URI` is set. Enable the Gmail API. The consent screen scopes are OpenID, email, profile, and Gmail readonly. Do not add send or modify.
3. Put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in the API environment. Leave `GOOGLE_REDIRECT_URI` empty to use `API_PUBLIC_URL`. Do not commit them.
4. Create a Pub/Sub topic, for example `projects/PROJECT_ID/topics/vigie-gmail`. Grant `gmail-api-push@system.gserviceaccount.com` the Pub/Sub Publisher role on that topic. Gmail's watch call publishes there.
5. Create a push subscription on that topic. The push endpoint is `{API_PUBLIC_URL}/api/integrations/gmail/pubsub`. Enable authentication and set the audience to that same URL. Note the push service account email.
6. Set `GMAIL_PUBSUB_TOPIC`, `GMAIL_PUBSUB_AUDIENCE`, and `GMAIL_PUBSUB_SERVICE_ACCOUNT`. The audience is the push URL. The service account is the identity Google puts on the push token.
7. After a business connects Gmail, VIGIE reads the current history id, syncs recent mail, calls `users.watch`, then reads history since that baseline so mail that arrives during registration is not skipped. The watch response's expiration is stored as Google returns it.
8. `POST /api/integrations/gmail/pubsub` accepts the push. It verifies the Google OIDC bearer token, checks that the subscription belongs to the same project as the topic, and only then reads `emailAddress` and `historyId`. The notification is not the email. VIGIE calls `history.list` and fetches the changed messages. An unknown mailbox is acknowledged and ignored. A repeated delivery does not create another message, event, commitment, or signal.
9. The endpoint requires HTTPS in production. Google will not push to a laptop address. Locally, use Connect and Sync now. Real-time listening stays "Not configured" until the three Pub/Sub variables are set.
10. Watches expire. Renew them before the stored expiration. Run `python -m app.jobs.renew_gmail_watches` once a day from the host scheduler. The command uses the expiration Google returned and `GMAIL_WATCH_RENEW_WITHIN_HOURS` (default 24). One mailbox that fails is recorded and the next mailbox still renews. No queue or cache is required. Disconnecting Gmail clears the mailbox id and the stored tokens, so a later notification is ignored.
11. If Gmail says the stored history id is gone, VIGIE syncs recent messages and stores a new history baseline. A failed watch leaves the mailbox connected, records the error, and can be retried with Turn on automatic updates. Disconnecting clears the stored watch, so a later notification for that mailbox is ignored. Google may keep publishing until the watch expires; VIGIE does not store those messages.

VIGIE does this automatically after the environment is set: start OAuth, bind and consume `state`, encrypt the tokens, store the mailbox on that business, register the watch, verify Pub/Sub, ignore unknown mailboxes and repeats, and renew watches from the daily command.

You configure Google Cloud: Gmail API, the OAuth client and consent screen, the redirect above, the Pub/Sub topic and the `gmail-api-push@system.gserviceaccount.com` publisher grant, and the authenticated push subscription whose endpoint and audience are `{API_PUBLIC_URL}/api/integrations/gmail/pubsub`.

You set on Render, for the API and the renewal cron: `API_PUBLIC_URL`, `CREDENTIAL_ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GMAIL_PUBSUB_TOPIC`, `GMAIL_PUBSUB_SERVICE_ACCOUNT`, and `GMAIL_PUBSUB_AUDIENCE` when it should not be derived. The cron command is `python -m app.jobs.renew_gmail_watches`.

## Microsoft OAuth

```text
MICROSOFT_CLIENT_ID
MICROSOFT_CLIENT_SECRET
MICROSOFT_TENANT_ID
MICROSOFT_REDIRECT_URI
```

Redirect URI:

```text
{API_PUBLIC_URL}/api/integrations/microsoft/callback
```

Leave `MICROSOFT_REDIRECT_URI` empty and set `API_PUBLIC_URL` to the public API origin. The API then uses that redirect. Set `MICROSOFT_REDIRECT_URI` only when the callback must differ from that derived URL. Production rejects an HTTP or localhost redirect.

The requested scope is `offline_access` and `https://graph.microsoft.com/Mail.Read`. VIGIE does not request `Mail.Send`. `POST /api/integrations/microsoft/sync` reads the latest Outlook messages through `GET https://graph.microsoft.com/v1.0/me/messages` and sends them through the same analysis pipeline as the other channels. There is no Microsoft push webhook. Sync now is how new mail is imported. An expired access token is refreshed with the stored refresh token. Disconnect deletes that credential, so a later sync does nothing.

`MICROSOFT_TENANT_ID` defaults to `common`. That uses `https://login.microsoftonline.com/common/oauth2/v2.0` and lets people from different Microsoft 365 organizations sign in, when the Entra app registration allows accounts in any organizational directory. Set it to one directory ID to restrict sign-in to that tenant. VIGIE still stores each mailbox on one business. Another business cannot sync it.

VIGIE does this automatically after the environment is set: start OAuth, bind and consume `state`, encrypt the tokens, store the mailbox on that business, refresh an expired access token, ignore a repeated message id, and refuse sync after disconnect.

You configure Microsoft Entra: an app registration, a client secret, the redirect above, delegated `Mail.Read` and `offline_access`, and admin consent when the customer's tenant requires it. For more than one organization, register the app as multi-tenant and leave `MICROSOFT_TENANT_ID` as `common`.

You set on Render: `API_PUBLIC_URL`, `CREDENTIAL_ENCRYPTION_KEY`, `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID`, and `MICROSOFT_REDIRECT_URI` when it should not be derived. Microsoft has no cron job.

This repository has not been tested against a live Microsoft account.

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
