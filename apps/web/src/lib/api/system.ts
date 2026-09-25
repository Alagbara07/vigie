import { apiGet, apiPost, isRecord, requiredNumber, requiredString } from "@/lib/api/client";

export type ProviderStatus = {
  provider: string;
  configured: boolean;
  model: string | null;
};

export type DemoMode = {
  enabled: boolean;
};

export type DemoRunResult = {
  business: string;
  messages_analyzed: number;
  signals_created: number;
  actions_created: number;
};

export function loadProviderStatus(): Promise<ProviderStatus> {
  return apiGet("/api/system/ai-provider", parseProviderStatus);
}

export function loadDemoMode(): Promise<DemoMode> {
  return apiGet("/api/system/demo", parseDemoMode);
}

export function runDemo(): Promise<DemoRunResult> {
  return apiPost("/api/demo/run", {}, parseDemoRun);
}

export function resetDemo(): Promise<void> {
  return apiPost("/api/demo/reset", {}, () => undefined);
}

export function parseProviderStatus(value: unknown): ProviderStatus {
  if (!isRecord(value)) {
    throw new Error("Expected a provider status");
  }
  const model = value.model;
  return {
    provider: requiredString(value, "provider"),
    configured: value.configured === true,
    model: typeof model === "string" && model.length > 0 ? model : null,
  };
}

function parseDemoMode(value: unknown): DemoMode {
  if (!isRecord(value)) {
    throw new Error("Expected demo mode");
  }
  return { enabled: value.enabled === true };
}

function parseDemoRun(value: unknown): DemoRunResult {
  if (!isRecord(value)) {
    throw new Error("Expected a demo result");
  }
  return {
    business: requiredString(value, "business"),
    messages_analyzed: requiredNumber(value, "messages_analyzed"),
    signals_created: requiredNumber(value, "signals_created"),
    actions_created: requiredNumber(value, "actions_created"),
  };
}
