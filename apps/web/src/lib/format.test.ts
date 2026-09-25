/// <reference types="vitest/globals" />
import { conversationWhen, formatMoney, givenName, greetingFor, relativeTime } from "@/lib/format";

describe("presentation formatting", () => {
  it("greets from the business timezone", () => {
    expect(greetingFor(new Date("2026-09-24T08:00:00+01:00"), "Africa/Lagos")).toBe("Good morning");
    expect(greetingFor(new Date("2026-09-24T15:00:00+01:00"), "Africa/Lagos")).toBe("Good afternoon");
    expect(greetingFor(new Date("2026-09-24T19:00:00+01:00"), "Africa/Lagos")).toBe("Good evening");
  });

  it("uses the business given name and naira amounts", () => {
    expect(givenName("Adaeze Wears")).toBe("Adaeze");
    expect(formatMoney("150000.00", "NGN")).toBe("₦150,000");
  });

  it("labels conversation days in the business timezone", () => {
    const now = new Date("2026-09-24T18:00:00+01:00");
    expect(conversationWhen("2026-09-24T07:30:00Z", "Africa/Lagos", now)).toBe("Today");
    expect(conversationWhen("2026-09-23T08:15:00Z", "Africa/Lagos", now)).toBe("Yesterday");
    expect(relativeTime("2026-09-24T16:00:00+01:00", now)).toBe("2 hours ago");
  });
});
