# How channels connect to VIGIE

The intelligence engine does not know which app a sentence came from. Adapters turn provider payloads into one message shape. Analysis, evaluation, signals, and approval stay the same.

## Current

```text
Demo connector
      ↓
Normalized message
      ↓
VIGIE
```

`POST /api/integrations/demo/messages` exists only when `VIGIE_DEMO_MODE=true`. It is labeled a WhatsApp Business prototype, not a live WhatsApp connection. The stored source is `demo`.

The same external message id is stored once for a business. A second delivery returns the existing message and does not create another event, commitment, signal, or recommendation.

## Production

```text
WhatsApp Business API
        ↓
WhatsApp adapter
        ↓
Normalized message
        ↓
VIGIE
```

```text
Gmail / Microsoft 365
        ↓
Email adapter
        ↓
Normalized message
        ↓
VIGIE
```

Provider login, webhook verification, and signature checks belong in those adapters. They do not belong in the analysis service. This build does not implement Meta, Google, or Microsoft OAuth.

Allowed sources are `whatsapp`, `gmail`, `microsoft365`, and `demo`. Any other source is rejected before a message is stored.
