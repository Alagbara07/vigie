/// <reference types="vitest/globals" />
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ApiError } from "@/lib/api/client";
import { applyTheme } from "@/lib/theme";

const nav = vi.hoisted(() => ({
  pathname: "/",
  replace: vi.fn(),
  push: vi.fn(),
}));

const auth = vi.hoisted(() => ({
  loadSession: vi.fn(),
  login: vi.fn(),
  signup: vi.fn(),
  logout: vi.fn(),
  createBusiness: vi.fn(),
  enterDemo: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ replace: nav.replace, push: nav.push }),
}));

vi.mock("@/lib/api/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/auth")>("@/lib/api/auth");
  return {
    ...actual,
    loadSession: auth.loadSession,
    login: auth.login,
    signup: auth.signup,
    logout: auth.logout,
    createBusiness: auth.createBusiness,
    enterDemo: auth.enterDemo,
  };
});

import { ActionReview } from "@/components/action-review";
import { AuthForm } from "@/components/auth-form";
import { DemoEntry } from "@/components/demo-entry";
import { IntegrationsPanel } from "@/components/integrations-panel";
import { OnboardingForm } from "@/components/onboarding-form";
import { BrandLink, PrimaryNav } from "@/components/primary-nav";
import { SessionGate, SessionProvider } from "@/components/session-provider";
import { ThemeToggle } from "@/components/theme-toggle";

const business = {
  id: "business-1",
  name: "Adaeze Wears",
  slug: "adaeze-wears",
  timezone: "Africa/Lagos",
  default_currency: "NGN",
  role: "owner",
};

const session = {
  user: { id: "user-1", email: "ada@example.com", name: "Ada" },
  businesses: [business],
  current_business: business,
};

describe("authentication flow", () => {
  beforeEach(() => {
    nav.pathname = "/";
    nav.replace.mockReset();
    nav.push.mockReset();
    auth.loadSession.mockReset();
    auth.login.mockReset();
    auth.signup.mockReset();
    auth.logout.mockReset();
    auth.createBusiness.mockReset();
    auth.enterDemo.mockReset();
    document.documentElement.removeAttribute("data-theme");
  });

  it("sends an unauthenticated visitor away from the command center", async () => {
    auth.loadSession.mockRejectedValue(new ApiError(401));
    render(
      <SessionProvider>
        <SessionGate>
          <p>Private desk</p>
        </SessionGate>
      </SessionProvider>,
    );

    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/login"));
    expect(screen.getByText("Checking your session")).toBeInTheDocument();
    expect(screen.queryByText("Private desk")).not.toBeInTheDocument();
  });

  it("opens the command center for a signed-in business", async () => {
    auth.loadSession.mockResolvedValue(session);
    render(
      <SessionProvider>
        <SessionGate>
          <p>Private desk</p>
        </SessionGate>
      </SessionProvider>,
    );

    expect(await screen.findByText("Private desk")).toBeInTheDocument();
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("sends a new account to onboarding", async () => {
    auth.loadSession.mockResolvedValue({ ...session, businesses: [], current_business: null });
    render(
      <SessionProvider>
        <SessionGate>
          <p>Private desk</p>
        </SessionGate>
      </SessionProvider>,
    );

    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/onboarding"));
  });

  it("keeps login public", async () => {
    nav.pathname = "/login";
    auth.loadSession.mockRejectedValue(new ApiError(401));
    render(
      <SessionProvider>
        <SessionGate>
          <p>Sign-in form</p>
        </SessionGate>
      </SessionProvider>,
    );

    expect(await screen.findByText("Sign-in form")).toBeInTheDocument();
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("signs in and signs up", async () => {
    auth.login.mockResolvedValue(session);
    render(<AuthForm mode="login" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "ada@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct-horse" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/"));

    auth.signup.mockResolvedValue({ ...session, businesses: [], current_business: null });
    render(<AuthForm mode="signup" />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Ada" } });
    fireEvent.change(screen.getAllByLabelText("Email")[1], { target: { value: "ada@example.com" } });
    fireEvent.change(screen.getAllByLabelText("Password")[1], { target: { value: "correct-horse" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/onboarding"));
  });

  it("shows an unauthorized login", async () => {
    auth.login.mockRejectedValue(new (await import("@/lib/api/auth")).AuthError(401));
    render(<AuthForm mode="login" />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "ada@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "nope" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("do not match");
  });

  it("hides the workspace from a signed-out visitor", async () => {
    auth.loadSession.mockRejectedValue(new ApiError(401));
    render(
      <SessionProvider>
        <BrandLink />
        <PrimaryNav />
      </SessionProvider>,
    );
    expect(await screen.findByRole("link", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "VIGIE" })).toHaveAttribute("href", "/about");
    expect(screen.getByRole("link", { name: "Demo" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "About" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Command Center" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Integrations" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Log out" })).not.toBeInTheDocument();
  });

  it("logs out", async () => {
    auth.loadSession.mockResolvedValue(session);
    auth.logout.mockResolvedValue(undefined);
    render(
      <SessionProvider>
        <BrandLink />
        <PrimaryNav />
      </SessionProvider>,
    );
    expect(await screen.findByRole("link", { name: "Command Center" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Integrations" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "VIGIE" })).toHaveAttribute("href", "/");
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    await waitFor(() => expect(auth.logout).toHaveBeenCalled());
  });

  it("creates a business during onboarding", async () => {
    auth.createBusiness.mockResolvedValue(undefined);
    render(<OnboardingForm />);
    fireEvent.change(screen.getByLabelText("Business name"), { target: { value: "North Shop" } });
    fireEvent.click(screen.getByRole("button", { name: "Create business" }));
    await waitFor(() => expect(auth.createBusiness).toHaveBeenCalledWith("North Shop"));
    expect(nav.push).toHaveBeenCalledWith("/");
  });

  it("keeps the demo entry separate from sign in", async () => {
    auth.enterDemo.mockResolvedValue(session);
    render(<DemoEntry />);
    expect(screen.getByRole("link", { name: "Sign In" })).toHaveAttribute("href", "/login");
    fireEvent.click(screen.getByRole("button", { name: "Try Demo" }));
    await waitFor(() => expect(auth.enterDemo).toHaveBeenCalled());
    expect(nav.push).toHaveBeenCalledWith("/");
  });

  it("hides integration controls and approval from a member", () => {
    render(<IntegrationsPanel demoEnabled={false} canManage={false} onSend={async () => {
      throw new Error("unused");
    }} />);
    expect(screen.getAllByText("You do not have permission to manage integrations.").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Connect Google" })).not.toBeInTheDocument();

    render(
      <ActionReview
        canDecide={false}
        action={{
          id: "action-1",
          business_id: "business-1",
          signal_id: "signal-1",
          action_type: "FOLLOW_UP_CUSTOMER",
          title: "Follow up",
          description: "The payment is past its due date.",
          status: "PROPOSED",
          proposed_content: "Ask Amaka about the balance.",
          approved_at: null,
          rejected_at: null,
          executed_at: null,
          signal: {
            id: "signal-1",
            title: "Payment overdue",
            signal_type: "OVERDUE_PAYMENT",
            financial_impact_amount: "150000",
            currency: "NGN",
          },
        }}
        onApprove={async () => undefined}
        onReject={async () => undefined}
      />,
    );
    expect(screen.getByText("You do not have permission to approve actions for this business.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("keeps the sign-in form usable in dark mode", () => {
    applyTheme("dark");
    render(
      <>
        <ThemeToggle />
        <AuthForm mode="login" />
      </>,
    );
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeInTheDocument();
  });
});
