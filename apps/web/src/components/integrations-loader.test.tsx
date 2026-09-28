import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IntegrationsLoader } from "@/components/integrations-loader";
import type { ChannelStatus } from "@/lib/api/integrations";

const loadChannels = vi.fn();
const loadSession = vi.fn();
const loadDemoMode = vi.fn();
const loadProviderStatus = vi.fn();
let connection = "microsoft365";
let provider = "";

vi.mock("next/navigation", () => ({
  useSearchParams: () =>
    new URLSearchParams(
      [connection ? `connection=${connection}` : "", provider ? `provider=${provider}` : ""].filter(Boolean).join("&"),
    ),
  usePathname: () => "/settings/integrations",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/api/auth", () => ({
  loadSession: () => loadSession(),
}));

vi.mock("@/lib/api/system", () => ({
  loadDemoMode: () => loadDemoMode(),
  loadProviderStatus: () => loadProviderStatus(),
  resetDemo: vi.fn(),
  runDemo: vi.fn(),
}));

vi.mock("@/lib/api/integrations", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/integrations")>("@/lib/api/integrations");
  return {
    ...actual,
    loadChannels: (...args: unknown[]) => loadChannels(...args),
    loadDemoMessages: vi.fn(async () => []),
  };
});

const session = {
  user: { id: "user-1", email: "ada@example.com", name: "Ada" },
  businesses: [
    {
      id: "biz-1",
      name: "Adaeze Wears",
      slug: "adaeze-wears",
      timezone: "Africa/Lagos",
      default_currency: "NGN",
      role: "owner",
    },
  ],
  current_business: {
    id: "biz-1",
    name: "Adaeze Wears",
    slug: "adaeze-wears",
    timezone: "Africa/Lagos",
    default_currency: "NGN",
    role: "owner",
  },
};

function microsoft(accountLabel: string | null, availability: ChannelStatus["availability"]): ChannelStatus {
  return {
    provider: "microsoft365",
    label: "Microsoft 365",
    description: "Analyze Outlook business conversations.",
    availability,
    configured: true,
    accountLabel,
    lastSyncAt: null,
    lastError: null,
  };
}

describe("IntegrationsLoader", () => {
  beforeEach(() => {
    connection = "microsoft365";
    provider = "";
    loadChannels.mockReset();
    loadSession.mockReset();
    loadDemoMode.mockReset();
    loadProviderStatus.mockReset();
    loadSession.mockResolvedValue(session);
    loadDemoMode.mockResolvedValue({ enabled: false });
    loadProviderStatus.mockResolvedValue(null);
  });

  it("loads the stored Outlook mailbox after Microsoft returns from OAuth", async () => {
    loadChannels.mockResolvedValue([microsoft("john@example.com", "connected")]);

    render(<IntegrationsLoader />);

    expect(await screen.findByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("Connected Outlook mailbox:")).toBeInTheDocument();
    expect(screen.getByText("john@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Microsoft" })).not.toBeInTheDocument();
    expect(screen.queryByText("Ready to connect")).not.toBeInTheDocument();
    expect(loadChannels).toHaveBeenCalledWith("biz-1");
  });

  it("fetches integrations again when the OAuth result changes", async () => {
    loadChannels
      .mockResolvedValueOnce([microsoft(null, "available")])
      .mockResolvedValueOnce([microsoft("john@example.com", "connected")]);

    const view = render(<IntegrationsLoader />);
    expect(await screen.findByRole("button", { name: "Connect Microsoft" })).toBeInTheDocument();
    expect(loadChannels).toHaveBeenCalledTimes(1);

    connection = "microsoft365-return";
    view.rerender(<IntegrationsLoader />);

    expect(await screen.findByText("john@example.com")).toBeInTheDocument();
    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Microsoft" })).not.toBeInTheDocument();
    expect(loadChannels).toHaveBeenCalledTimes(2);
  });

  it("refetches integrations when the page is restored from the browser cache", async () => {
    loadChannels
      .mockResolvedValueOnce([microsoft(null, "available")])
      .mockResolvedValueOnce([microsoft("john@example.com", "connected")]);

    render(<IntegrationsLoader />);
    expect(await screen.findByRole("button", { name: "Connect Microsoft" })).toBeInTheDocument();

    await act(async () => {
      window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    });

    expect(await screen.findByText("john@example.com")).toBeInTheDocument();
    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(loadChannels).toHaveBeenCalledTimes(2);
  });

  it("explains a failed Microsoft connection without showing the mailbox as connected", async () => {
    connection = "error";
    provider = "microsoft365";
    loadChannels.mockResolvedValue([microsoft(null, "available")]);

    render(<IntegrationsLoader />);

    expect(await screen.findByRole("status")).toHaveTextContent("Microsoft 365 couldn't be connected.");
    const card = screen.getByRole("heading", { name: "Microsoft 365" }).closest("section");
    expect(card).toHaveTextContent("Needs attention");
    expect(card).toHaveTextContent("We couldn't connect your Microsoft 365 account. Please try again.");
    expect(screen.getByRole("button", { name: "Connect Microsoft" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reconnect Microsoft" })).not.toBeInTheDocument();
    expect(screen.queryByText("Ready to connect")).not.toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
    expect(loadChannels).toHaveBeenCalledWith("biz-1");
  });

  it("keeps a failed Microsoft reconnect on needs attention", async () => {
    connection = "error";
    provider = "microsoft365";
    loadChannels.mockResolvedValue([microsoft("ada@example.com", "error")]);

    render(<IntegrationsLoader />);

    expect(await screen.findByRole("status")).toHaveTextContent("Microsoft 365 couldn't be connected.");
    const card = screen.getByRole("heading", { name: "Microsoft 365" }).closest("section");
    expect(card).toHaveTextContent("Needs attention");
    expect(card).toHaveTextContent("We couldn't connect your Microsoft 365 account. Please try again.");
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconnect Microsoft" })).toBeInTheDocument();
    expect(screen.queryByText("Ready to connect")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
    expect(loadChannels).toHaveBeenCalledWith("biz-1");
  });

  it("keeps a Google OAuth error inside Google Workspace when the page reloads", async () => {
    connection = "error";
    provider = "gmail";
    loadChannels.mockResolvedValue([
      microsoft(null, "available"),
      {
        provider: "gmail",
        label: "Google Workspace",
        description: "Analyze business email conversations.",
        availability: "available",
        configured: true,
        accountLabel: null,
        lastSyncAt: null,
        lastError: null,
      },
      {
        provider: "whatsapp",
        label: "WhatsApp Business",
        description: "Monitor customer conversations.",
        availability: "available",
        configured: true,
        accountLabel: null,
        lastSyncAt: null,
        lastError: null,
      },
    ]);

    render(<IntegrationsLoader />);

    expect(await screen.findByRole("status")).toHaveTextContent("Google Workspace couldn't be connected.");
    const google = screen.getByRole("heading", { name: "Google Workspace" }).closest("section");
    const outlook = screen.getByRole("heading", { name: "Microsoft 365" }).closest("section");
    const whatsapp = screen.getByRole("heading", { name: "WhatsApp Business" }).closest("section");
    expect(google).toHaveTextContent("Needs attention");
    expect(google).toHaveTextContent("We couldn't connect your Google account. Please try again.");
    expect(screen.getByRole("button", { name: "Connect Google" })).toBeInTheDocument();
    expect(outlook).toHaveTextContent("Ready to connect");
    expect(outlook).not.toHaveTextContent("We couldn't connect your Google account");
    expect(outlook).not.toHaveTextContent("We couldn't connect your Microsoft 365 account");
    expect(whatsapp).not.toHaveTextContent("We couldn't connect");
  });
});
