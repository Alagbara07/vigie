export type HealthResponse = {
  status: "ok" | "degraded";
  service: string;
  api: "ok";
  database: "ok" | "unavailable";
};

export function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const record = value as Record<string, unknown>;
  return (
    (record.status === "ok" || record.status === "degraded") &&
    record.api === "ok" &&
    (record.database === "ok" || record.database === "unavailable") &&
    typeof record.service === "string"
  );
}
