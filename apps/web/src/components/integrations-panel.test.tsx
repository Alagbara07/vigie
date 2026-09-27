/// <reference types="vitest/globals" />
import { act, fireEvent, render, screen } from "@testing-library/react";

import { IntegrationsPanel } from "@/components/integrations-panel";
import { ApiError } from "@/lib/api/client";
import type { ChannelStatus } from "@/lib/api/integrations";

const result = {
  created: true,
  analyzed: true,
  message_id: "message-1",
  source: "demo",
  source_label: "WhatsApp Business",
  connection: "Demo connection",
  customer_name: "Amaka Bello",
  text: "I'll pay the remaining ₦150,000 on Friday.",
  occurred_at: "2026-09-24T09:00:00+01:00",
  external_message_id: "demo-wa-001",
  events: ["PAYMENT_COMMITMENT"],
};

describe("integrations", () => {
  it("shows the prototype channels without live provider buttons", () => {
    render(<IntegrationsPanel demoEnabled onSend={async () => result} />);

    expect(screen.getByRole("heading", { name: "Connect your business channels" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Demo WhatsApp" })).toBeInTheDocument();
    expect(screen.getByText("Prototype")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "WhatsApp Business" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Google Workspace" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Microsoft 365" })).toBeInTheDocument();
    expect(screen.getAllByText("Not configured")).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Coming soon" })).not.toBeInTheDocument();
    expect(screen.queryByText("WhatsApp Connected")).not.toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
  });

  it("asks for configuration before it will connect a real channel", () => {
    render(<IntegrationsPanel demoEnabled onSend={async () => result} />);

    fireEvent.click(screen.getByRole("button", { name: "Connect WhatsApp" }));
    fireEvent.click(screen.getByRole("button", { name: "Connect Google" }));
    fireEvent.click(screen.getByRole("button", { name: "Connect Microsoft" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Configuration required.");
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
  });

  it("shows a connected account and can disconnect it", async () => {
    const onDisconnect = vi.fn(async () => undefined);
    render(
      <IntegrationsPanel
        demoEnabled
        channels={whatsapp({ availability: "connected", configured: true, accountLabel: "Adaeze line" })}
        onSend={async () => result}
        onDisconnect={onDisconnect}
      />,
    );

    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("Account Adaeze line")).toBeInTheDocument();
    expect(screen.queryByText("WhatsApp Connected")).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    });
    expect(onDisconnect).toHaveBeenCalledWith("whatsapp");
  });

  it("shows a provider error without claiming the channel is connected", () => {
    render(
      <IntegrationsPanel
        demoEnabled
        channels={whatsapp({ availability: "error", configured: true, lastError: "VIGIE could not sync WhatsApp." })}
        onSend={async () => result}
      />,
    );

    expect(screen.getByText("Error")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("VIGIE could not sync WhatsApp.");
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
  });

  it("opens the demo connection and sends a test message", async () => {
    const onSend = vi.fn(async () => result);
    render(<IntegrationsPanel demoEnabled onSend={onSend} />);

    fireEvent.click(screen.getByRole("button", { name: "Demo connection" }));
    expect(screen.getByText("Demo connection active")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Send to VIGIE" }));

    expect(await screen.findByText("Message received. VIGIE is analyzing the conversation.")).toBeInTheDocument();
    expect(onSend).toHaveBeenCalledWith({
      customerName: "Amaka Bello",
      text: "I'll pay the remaining ₦150,000 on Friday.",
    });
    expect(screen.getByText("Payment commitment detected")).toBeInTheDocument();
  });

  it("explains when the demo connector cannot receive the message", async () => {
    render(
      <IntegrationsPanel
        demoEnabled
        initiallyConnected
        onSend={async () => {
          throw new ApiError(503);
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Send to VIGIE" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("VIGIE couldn't receive that message. Please try again.");
  });

  it("shows Gmail listening only when a watch is registered", async () => {
    const onSync = vi.fn(async () => undefined);
    const onEnableListening = vi.fn(async () => undefined);
    const received = new Date(Date.now() - 2 * 60 * 1000).toISOString();
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={gmail({
          availability: "connected",
          configured: true,
          accountLabel: "ada@example.com",
          listening: true,
          realtime: "listening",
          lastNotificationAt: received,
          pubsubConfigured: true,
        })}
        onSend={async () => result}
        onSync={onSync}
        onEnableListening={onEnableListening}
        onDisconnect={async () => undefined}
      />,
    );

    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("Listening for new messages")).toBeInTheDocument();
    expect(screen.getByText(/Last received:/)).toBeInTheDocument();
    expect(screen.queryByText("Real-time listening: Not configured")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enable real-time listening" })).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Sync now" }));
    });
    expect(onSync).toHaveBeenCalledWith("gmail");
  });

  it("keeps manual Gmail sync honest when Pub/Sub is not configured", async () => {
    const onEnableListening = vi.fn(async () => undefined);
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={gmail({
          availability: "connected",
          configured: true,
          realtime: "manual",
          listening: false,
          pubsubConfigured: false,
        })}
        onSend={async () => result}
        onEnableListening={onEnableListening}
      />,
    );

    expect(screen.getByText("Manual sync available")).toBeInTheDocument();
    expect(screen.getByText("Real-time listening: Not configured")).toBeInTheDocument();
    expect(screen.queryByText("Listening for new messages")).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Enable real-time listening" }));
    });
    expect(onEnableListening).toHaveBeenCalledWith("gmail");
  });

  it("shows a Gmail watch problem without claiming it is listening", () => {
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={gmail({
          availability: "connected",
          configured: true,
          realtime: "needs_attention",
          listening: false,
          lastError: "Real-time listening could not be enabled.",
        })}
        onSend={async () => result}
      />,
    );

    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Real-time listening could not be enabled.");
    expect(screen.queryByText("Listening for new messages")).not.toBeInTheDocument();
  });

  it("keeps channel cards readable when dark mode is on", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    render(<IntegrationsPanel demoEnabled initiallyConnected onSend={async () => result} />);

    expect(screen.getByLabelText("Customer")).toHaveClass("bg-[var(--paper)]", "text-[var(--ink)]");
    expect(screen.getByLabelText("Message")).toHaveClass("bg-[var(--paper)]", "text-[var(--ink)]");
    document.documentElement.removeAttribute("data-theme");
  });

  it("keeps the Gmail card readable in dark mode", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={gmail({ availability: "connected", configured: true, listening: true, realtime: "listening" })}
        onSend={async () => result}
      />,
    );

    expect(screen.getByText("Listening for new messages")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sync now" })).toHaveClass("bg-[var(--panel)]", "text-[var(--ink)]");
    expect(screen.getByRole("heading", { name: "Google Workspace" }).closest("section")).toHaveClass("bg-[var(--panel)]");
    document.documentElement.removeAttribute("data-theme");
  });
});

function gmail(overrides: Partial<ChannelStatus>): ChannelStatus[] {
  return [
    {
      provider: "gmail",
      label: "Google Workspace",
      description: "Analyze business email conversations.",
      availability: "not_configured",
      accountLabel: null,
      lastSyncAt: null,
      lastError: null,
      configured: false,
      listening: false,
      realtime: "not_configured",
      lastNotificationAt: null,
      pubsubConfigured: false,
      ...overrides,
    },
  ];
}

function whatsapp(overrides: Partial<ChannelStatus>): ChannelStatus[] {
  return [
    {
      provider: "whatsapp",
      label: "WhatsApp Business",
      description: "Monitor customer conversations and identify commitments, payment claims and requests.",
      availability: "not_configured",
      accountLabel: null,
      lastSyncAt: null,
      lastError: null,
      configured: false,
      ...overrides,
    },
  ];
}
