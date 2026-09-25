import { apiGet, isRecord, requiredString } from "@/lib/api/client";

export type ProviderStatus = {
  provider: string;
  configured: boolean;
  model: string | null;
};

export function loadProviderStatus(): Promise<ProviderStatus> {
  return apiGet("/api/system/ai-provider", parseProviderStatus);
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
