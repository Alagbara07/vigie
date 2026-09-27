# VIGIE demo

Open [http://localhost:3000](http://localhost:3000). Demo mode should be on (`VIGIE_DEMO_MODE=true`). If the board is stale, choose **Run demo**. That resets Adaeze Wears and replays the story. Actions come back as proposals, not approvals.

## Opening

Businesses don't have an information problem. They have an attention problem.

## Message

Amaka wrote: "I'll pay the remaining ₦150,000 on Friday."

VIGIE does not file that as another chat line. It stores a payment commitment for ₦150,000, due Friday, in Africa/Lagos.

The same inbox has two other messages worth showing for a moment.

Chinedu wrote: "I sent the ₦150,000 balance yesterday. Please confirm." That is a payment claim. `payment_verified` stays false. VIGIE does not treat "I sent it" as money received.

Tunde wrote: "Good morning." That creates no event, no commitment, no signal, and no action.

## Time

The demo does not wait for a real Friday. Evaluation is run twice with explicit reference times: the morning before the due day, then the morning after it. The machine clock stays alone.

## Signal

The board shows **Payment overdue** and **₦150,000** revenue at risk.

## Reasoning

Open the signal. The original sentence is on the page, with the missed commitment beside it. The recommendation sits under the evidence.

## Recommendation

The proposed step is to follow up with Amaka. The draft asks her to confirm once the payment has been made. It does not say the money arrived.

## Human control

Approve it.

VIGIE recommended the action. The business owner made the decision. No message was sent.

The presenter notes for this walkthrough live in `docs/HACKATHON_QA.md`.
