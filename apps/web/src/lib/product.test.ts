/// <reference types="vitest/globals" />
import { attentionHeadline, countOpen, detectedAs, stateLabel, whatHappened, whyItMatters } from "@/lib/product";

describe("product language", () => {
  it("counts attention from the supplied figures", () => {
    expect(attentionHeadline(2)).toBe("2 things need your attention");
    expect(attentionHeadline(1)).toBe("1 thing needs your attention");
    expect(
      countOpen(
        [
          { status: "OPEN", signal_type: "OVERDUE_PAYMENT" },
          { status: "RESOLVED", signal_type: "OVERDUE_PAYMENT" },
          { status: "OPEN", signal_type: "UNANSWERED_REQUEST" },
        ],
        "OVERDUE_PAYMENT",
      ),
    ).toBe(1);
  });

  it("describes a missed payment from the signal amount", () => {
    const signal = {
      signal_type: "OVERDUE_PAYMENT",
      title: "Payment overdue",
      description: "Amaka Bello promised NGN 150000 by Friday.",
      financial_impact_amount: "150000.00",
      currency: "NGN",
    };
    expect(whatHappened(signal)).toBe("₦150,000 payment commitment was missed.");
    expect(whyItMatters(signal)).toContain("₦150,000 of revenue at risk");
    expect(detectedAs("PAYMENT_COMMITMENT")).toBe("Payment commitment");
    expect(stateLabel("MISSED")).toBe("Missed");
    expect(stateLabel("PROPOSED")).toBe("Proposed");
  });
});
