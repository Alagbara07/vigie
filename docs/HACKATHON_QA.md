# Questions a judge may ask

## Why not just use ChatGPT?

A chat reply disappears. VIGIE keeps a payment promise, a due date, and the later fact that the promise was missed. The model only proposes what the message appears to say. Validation and the domain engine decide what is stored, and evaluation uses the business clock rather than another prompt.

## Why NVIDIA?

NVIDIA is one provider behind the same proposal schema as the local heuristic. The heuristic needs no network and is what the automated tests run. NVIDIA is selected with `AI_PROVIDER=nvidia` and is not a silent fallback. The domain rules do not change when the provider changes.

## What happens if the AI is wrong?

A malformed response is rejected and writes no event, commitment, signal, or action. A payment claim cannot set `payment_verified`. The signal page shows the original message, so the owner can see the evidence before approving anything.

## Why not automatically send messages?

Approving a recommendation records that the owner agreed. `executed_at` stays empty. Sending a WhatsApp or email is a later, separate step. The owner remains the one who contacts the customer.

## How do you prevent duplicate signals?

Re-running analysis, evaluation, or recommendation hits database uniqueness: one event per message and type, one commitment per source message and type, one open signal per commitment or event, and one action per signal and type. A second approval of the same action is rejected.

## How does VIGIE scale?

The current path is a single API and PostgreSQL, on purpose. Events, commitments, signals, and actions are already separate records. A queue or worker can call the same services later without turning the model into the system of record.

## What is the moat?

The valuable part is the business memory: what was promised, whether it is still open, what evidence it came from, and which action a person accepted. Using a model is the interpretation step, not the product.
