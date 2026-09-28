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
    expect(screen.getByRole("button", { name: "Configure Google" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Configure Microsoft" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Configure WhatsApp" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Coming soon" })).not.toBeInTheDocument();
    expect(screen.queryByText("WhatsApp Connected")).not.toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
  });

  it("asks for configuration before it will connect a real channel", () => {
    render(<IntegrationsPanel demoEnabled onSend={async () => result} />);

    fireEvent.click(screen.getByRole("button", { name: "Configure WhatsApp" }));
    fireEvent.click(screen.getByRole("button", { name: "Configure Google" }));
    fireEvent.click(screen.getByRole("button", { name: "Configure Microsoft" }));

    expect(screen.getByRole("alert")).toHaveTextContent("This channel is not set up yet.");
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
    expect(screen.getByText("Connected WhatsApp number:")).toBeInTheDocument();
    expect(screen.getByText("Adaeze line")).toBeInTheDocument();
    expect(screen.queryByText("Available")).not.toBeInTheDocument();
    expect(screen.queryByText("WhatsApp Connected")).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    });
    expect(onDisconnect).toHaveBeenCalledWith("whatsapp");
  });

  it("explains Gmail OAuth without claiming a mailbox is connected", () => {
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={gmail({ availability: "available", configured: true })}
        onSend={async () => result}
      />,
    );

    expect(screen.getByText("Ready to connect")).toBeInTheDocument();
    expect(screen.getByText("Connect Google Workspace to bring a Gmail mailbox into this business.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect Google" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
    expect(screen.queryByText("Available")).not.toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
    expect(screen.queryByText("Listening for new messages")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Configure Google" })).not.toBeInTheDocument();
  });

  it("asks to configure Google before a mailbox can be connected", () => {
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={gmail({ availability: "not_configured", configured: false })}
        onSend={async () => result}
      />,
    );

    const card = screen.getByRole("heading", { name: "Google Workspace" }).closest("section");
    expect(card).toHaveTextContent("Not configured");
    expect(screen.getByText("Connect Google Workspace to let VIGIE analyze business email conversations.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Configure Google" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
    expect(screen.queryByText("Ready to connect")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Google" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
  });

  it("shows Connecting while Google sign-in is starting", () => {
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={gmail({ availability: "available", configured: true })}
        onSend={async () => result}
        onStartOauth={() => undefined}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Connect Google" }));

    expect(screen.getByText("Connecting")).toBeInTheDocument();
    expect(screen.getByText("Connecting your Google account...")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Google" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
    expect(screen.queryByText("Listening for new messages")).not.toBeInTheDocument();
  });

  it("shows the connected Gmail mailbox and can sync or disconnect it", async () => {
    const onSync = vi.fn(async () => undefined);
    const onDisconnect = vi.fn(async () => undefined);
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={gmail({
          availability: "connected",
          configured: true,
          accountLabel: "john@example.com",
          listening: false,
          realtime: "manual",
        })}
        onSend={async () => result}
        onSync={onSync}
        onDisconnect={onDisconnect}
      />,
    );

    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("Connected Gmail mailbox:")).toBeInTheDocument();
    expect(screen.getByText("john@example.com")).toBeInTheDocument();
    expect(screen.getByText("VIGIE imports messages for analysis. VIGIE does not send email.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Google" })).not.toBeInTheDocument();
    expect(screen.queryByText("Listening for new messages")).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Sync now" }));
    });
    expect(onSync).toHaveBeenCalledWith("gmail");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    });
    expect(onDisconnect).toHaveBeenCalledWith("gmail");
  });

  it("shows Syncing instead of Sync now while Gmail is importing", async () => {
    let finish: () => void = () => undefined;
    const onSync = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finish = () => resolve();
        }),
    );
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={gmail({
          availability: "connected",
          configured: true,
          accountLabel: "john@example.com",
        })}
        onSend={async () => result}
        onSync={onSync}
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Sync now" }));
    });

    expect(await screen.findByText("Syncing")).toBeInTheDocument();
    expect(screen.getByText("Importing new messages...")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
    expect(screen.queryByText("Listening for new messages")).not.toBeInTheDocument();
    await act(async () => {
      finish();
    });
  });

  it("shows Disconnecting and hides conflicting actions", async () => {
    let finish: () => void = () => undefined;
    const onDisconnect = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finish = () => resolve();
        }),
    );
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={gmail({
          availability: "connected",
          configured: true,
          accountLabel: "john@example.com",
        })}
        onSend={async () => result}
        onDisconnect={onDisconnect}
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    });

    expect(screen.getByText("Disconnecting")).toBeInTheDocument();
    expect(screen.getByText("Removing this connection...")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Google" })).not.toBeInTheDocument();
    await act(async () => {
      finish();
    });
  });

  it("asks to reconnect Google when the mailbox needs attention", () => {
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={gmail({
          availability: "error",
          configured: true,
          accountLabel: "name@example.com",
          lastSyncAt: "2026-09-28T12:00:00Z",
          lastError: "Configuration required.",
          realtime: "needs_attention",
        })}
        onSend={async () => result}
      />,
    );

    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("Your Google account needs to be reconnected before VIGIE can continue importing email.")).toBeInTheDocument();
    expect(screen.getByText("Connected Gmail mailbox:")).toBeInTheDocument();
    expect(screen.getByText("name@example.com")).toBeInTheDocument();
    expect(screen.getByText("Last successful sync: 28 Sept 2026")).toBeInTheDocument();
    expect(screen.getByText("Automatic updates are paused until you reconnect.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconnect Google" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
    const card = screen.getByRole("heading", { name: "Google Workspace" }).closest("section");
    expect(card).not.toHaveTextContent("This channel is not set up yet");
    expect(card).not.toHaveTextContent("Not configured");
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
    expect(screen.queryByText("Listening for new messages")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
  });

  it("says the Gmail watch is not active when listening has stopped", () => {
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={gmail({
          availability: "connected",
          configured: true,
          accountLabel: "ada@example.com",
          listening: false,
          realtime: "needs_attention",
        })}
        onSend={async () => result}
      />,
    );

    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("Connected Gmail mailbox:")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("Automatic updates are paused. Sync now still imports mail.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
    expect(screen.queryByText("Available")).not.toBeInTheDocument();
    expect(screen.queryByText("Listening for new messages")).not.toBeInTheDocument();
  });

  it("explains Microsoft OAuth without claiming a mailbox is connected", () => {
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={microsoft({ availability: "available", configured: true })}
        onSend={async () => result}
      />,
    );

    expect(screen.getByText("Ready to connect")).toBeInTheDocument();
    expect(screen.getByText("Connect Microsoft 365 to bring an Outlook mailbox into this business.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect Microsoft" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
    expect(screen.queryByText("Available")).not.toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
  });

  it("shows the connected Outlook mailbox and can sync it", async () => {
    const onSync = vi.fn(async () => undefined);
    const onDisconnect = vi.fn(async () => undefined);
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={microsoft({
          availability: "connected",
          configured: true,
          accountLabel: "ada@example.com",
        })}
        onSend={async () => result}
        onSync={onSync}
        onDisconnect={onDisconnect}
      />,
    );

    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("Connected Outlook mailbox:")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("VIGIE imports messages for analysis. VIGIE does not send email.")).toBeInTheDocument();
    expect(screen.queryByText("Available")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Microsoft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enable real-time listening" })).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Sync now" }));
    });
    expect(onSync).toHaveBeenCalledWith("microsoft365");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    });
    expect(onDisconnect).toHaveBeenCalledWith("microsoft365");
  });

  it("shows syncing instead of Sync now while Outlook is importing", async () => {
    let finish: () => void = () => undefined;
    const onSync = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          finish = () => resolve();
        }),
    );
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={microsoft({
          availability: "connected",
          configured: true,
          accountLabel: "ada@example.com",
        })}
        onSend={async () => result}
        onSync={onSync}
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Sync now" }));
    });

    expect(await screen.findByText("Syncing")).toBeInTheDocument();
    expect(screen.getByText("Importing new messages...")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Microsoft" })).not.toBeInTheDocument();
    await act(async () => {
      finish();
    });
  });

  it("returns Microsoft to ready to connect after disconnect", () => {
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={microsoft({ availability: "disconnected", configured: true, accountLabel: "ada@example.com" })}
        onSend={async () => result}
      />,
    );

    expect(screen.getByText("Ready to connect")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect Microsoft" })).toBeInTheDocument();
    expect(screen.queryByText("ada@example.com")).not.toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
  });

  it("asks to reconnect Microsoft when the mailbox needs attention", () => {
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={microsoft({
          availability: "error",
          configured: true,
          accountLabel: "ada@example.com",
          lastSyncAt: "2026-09-28T12:00:00Z",
          lastError: "Configuration required.",
        })}
        onSend={async () => result}
      />,
    );

    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("Your Microsoft account needs to be reconnected before VIGIE can continue importing email.")).toBeInTheDocument();
    expect(screen.getByText("Connected Outlook mailbox:")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("Last successful sync: 28 Sept 2026")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconnect Microsoft" })).toBeInTheDocument();
    const card = screen.getByRole("heading", { name: "Microsoft 365" }).closest("section");
    expect(card).not.toHaveTextContent("This channel is not set up yet");
    expect(card).not.toHaveTextContent("Not configured");
    expect(screen.queryByText("Available")).not.toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
  });

  it("explains the Meta setup and does not call an unconnected number connected", () => {
    render(
      <IntegrationsPanel
        demoEnabled={false}
        channels={whatsapp({
          availability: "available",
          configured: true,
          webhookUrl: "https://vigie-api.example/api/integrations/whatsapp/webhook",
        })}
        onSend={async () => result}
      />,
    );

    expect(screen.getByText("Ready to connect")).toBeInTheDocument();
    expect(screen.queryByText("Available")).not.toBeInTheDocument();
    expect(screen.getByText(/does not send a reply/i)).toBeInTheDocument();
    expect(screen.getByText("https://vigie-api.example/api/integrations/whatsapp/webhook")).toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
  });

  it("shows a provider error without claiming the channel is connected", () => {
    render(
      <IntegrationsPanel
        demoEnabled
        channels={whatsapp({
          availability: "error",
          configured: true,
          accountLabel: "+2348000000000",
          lastError: "Configuration required.",
        })}
        onSend={async () => result}
      />,
    );

    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Your WhatsApp number needs to be reconnected before VIGIE can continue receiving messages.",
    );
    expect(screen.queryByText("This channel is not set up yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("Not configured")).not.toBeInTheDocument();
    expect(screen.getByText("Connected WhatsApp number:")).toBeInTheDocument();
    expect(screen.getByText("+2348000000000")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sync now" })).not.toBeInTheDocument();
    expect(screen.queryByText("Available")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconnect WhatsApp" })).toBeInTheDocument();
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
  });

  it("opens the demo connection and sends a test message", async () => {
    const onSend = vi.fn(async () => result);
    render(<IntegrationsPanel demoEnabled onSend={onSend} />);

    fireEvent.click(screen.getByRole("button", { name: "Demo connection" }));
    expect(screen.getByText("Demo connection active")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Send to VIGIE" }));

    expect(await screen.findByText("Message received. Analyzing the conversation...")).toBeInTheDocument();
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

    expect(await screen.findByRole("alert")).toHaveTextContent("VIGIE couldn't receive that message. Try again.");
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

    expect(screen.getByText("New mail is imported when you sync.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Turn on automatic updates" })).toBeInTheDocument();
    expect(screen.queryByText("Listening for new messages")).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Turn on automatic updates" }));
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

    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("Automatic updates are paused. Sync now still imports mail.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Automatic updates could not be turned on. Try again.");
    expect(screen.queryByText("Available")).not.toBeInTheDocument();
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

function microsoft(overrides: Partial<ChannelStatus>): ChannelStatus[] {
  return [
    {
      provider: "microsoft365",
      label: "Microsoft 365",
      description: "Analyze Outlook business conversations.",
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
