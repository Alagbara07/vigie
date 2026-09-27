# Questions a judge may ask

## Why does this need AI?

The messages are unstructured. A person does not label them as a promise, a claim, or a question. The model proposes that reading. Everything after that proposal is ordinary application logic.

## Why not just use ChatGPT?

A chat reply disappears. VIGIE keeps the promise, the due date, and the later fact that it was missed. The next run does not have to ask the model what already happened.

## Why NVIDIA?

NVIDIA is one provider behind the same proposal schema as the local heuristic. Tests run on the heuristic and do not need a network. `AI_PROVIDER=nvidia` selects NVIDIA. The domain rules stay the same.

## What happens if the AI is wrong?

The owner sees the original message next to the recommendation and can reject it. Approval only records that decision. It does not contact the customer.

## How do you prevent hallucinated business events?

The model cannot write the database. Its JSON must match `MessageAnalysisProposal`. Unknown fields, a wrong provider label, and a signal type posed as an event are rejected. A payment claim cannot set `payment_verified`. Dates are resolved by the application from the spoken weekday and `Africa/Lagos`, not from a calendar date the model invents.

## How do you prevent duplicate signals?

The database allows one event per message and type, one commitment per source message and type, one open signal per commitment or event, and one action per signal and type. Running analysis, evaluation, or recommendation again reuses those rows.

## Why is human approval required?

The recommendation may be wrong, or the owner may already have handled it. Approval means the owner accepted the recommendation. `executed_at` stays empty.

## How would this scale?

The current system is one API and PostgreSQL. Events, commitments, signals, and actions are already separate records. A queue can call the same services later. The model would still not be the system of record.

## What happens if NVIDIA goes down?

The request fails with a provider error. VIGIE does not silently switch to the heuristic, so the screen cannot claim NVIDIA intelligence while another provider did the work. The local demo keeps working when `AI_PROVIDER=heuristic`.

## What is the long-term business model?

A small business pays for attention on the conversations it already has: which promises are open, which requests are waiting, and which action is worth taking. Sending the message can be a later, separately priced step. That step is not built.

## What is defensible about VIGIE?

The record of what was promised, whether it is still open, which message is the evidence, and which action a person accepted. The model is the interpretation step.

## What would you build next?

Delivery of an approved message on a channel the business already uses, then a way to mark the commitment fulfilled from a later message. Not a second chatbot.
