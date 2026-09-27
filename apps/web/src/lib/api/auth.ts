import { ApiError, isRecord, requiredString } from "@/lib/api/client";

export type MembershipBusiness = {
  id: string;
  name: string;
  slug: string;
  timezone: string;
  default_currency: string;
  role: string;
};

export type SessionState = {
  user: { id: string; email: string; name: string };
  businesses: MembershipBusiness[];
  current_business: MembershipBusiness | null;
};

export class AuthError extends Error {
  readonly status: number;

  constructor(status: number, message?: string) {
    super(message ?? messageFor(status));
    this.name = "AuthError";
    this.status = status;
  }
}

export async function loadSession(): Promise<SessionState> {
  const response = await fetch("/api/auth/session", { cache: "no-store", credentials: "include" });
  if (!response.ok) {
    throw new ApiError(response.status);
  }
  return parseSession(await response.json());
}

export async function signup(input: { email: string; name: string; password: string }): Promise<SessionState> {
  return send("/api/auth/signup", input);
}

export async function login(input: { email: string; password: string }): Promise<SessionState> {
  return send("/api/auth/login", input);
}

export async function logout(): Promise<void> {
  const response = await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
  if (!response.ok && response.status !== 204) {
    throw new AuthError(response.status);
  }
}

export async function enterDemo(): Promise<SessionState> {
  return send("/api/auth/demo", {});
}

export async function createBusiness(name: string): Promise<void> {
  const response = await fetch("/api/businesses", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw new AuthError(
      response.status,
      response.status === 409 ? "A business with this name already exists." : undefined,
    );
  }
}

async function send(path: string, body: unknown): Promise<SessionState> {
  const response = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new AuthError(response.status);
  }
  return parseSession(await response.json());
}

export function parseSession(value: unknown): SessionState {
  if (!isRecord(value) || !isRecord(value.user)) {
    throw new Error("Expected a session");
  }
  return {
    user: {
      id: requiredString(value.user, "id"),
      email: requiredString(value.user, "email"),
      name: requiredString(value.user, "name"),
    },
    businesses: Array.isArray(value.businesses) ? value.businesses.map(parseBusiness) : [],
    current_business: value.current_business == null ? null : parseBusiness(value.current_business),
  };
}

function parseBusiness(value: unknown): MembershipBusiness {
  if (!isRecord(value)) {
    throw new Error("Expected a business");
  }
  return {
    id: requiredString(value, "id"),
    name: requiredString(value, "name"),
    slug: requiredString(value, "slug"),
    timezone: requiredString(value, "timezone"),
    default_currency: requiredString(value, "default_currency"),
    role: requiredString(value, "role"),
  };
}

function messageFor(status: number): string {
  if (status === 401) {
    return "That email and password do not match.";
  }
  if (status === 409) {
    return "An account with this email already exists.";
  }
  if (status === 404) {
    return "Demo mode is not available.";
  }
  return "VIGIE couldn't complete that request.";
}
