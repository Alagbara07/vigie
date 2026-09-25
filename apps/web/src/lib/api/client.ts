export class ApiError extends Error {
  readonly status: number | null;

  constructor(status: number | null = null) {
    super("VIGIE can't reach the intelligence service.");
    this.name = "ApiError";
    this.status = status;
  }
}

export class MissingBusinessError extends Error {
  constructor() {
    super("Adaeze Wears isn't available in this workspace yet.");
    this.name = "MissingBusinessError";
  }
}

export async function apiGet<T>(path: string, parse: (value: unknown) => T): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { cache: "no-store" });
  } catch {
    throw new ApiError();
  }
  if (!response.ok) {
    throw new ApiError(response.status);
  }
  try {
    return parse(await response.json());
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(response.status);
  }
}

export async function apiPost<T>(path: string, body: unknown, parse: (value: unknown) => T): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError();
  }
  if (!response.ok) {
    throw new ApiError(response.status);
  }
  try {
    return parse(await response.json());
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(response.status);
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function requiredString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`Missing ${key}`);
  }
  return value;
}

export function requiredNumber(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`Missing ${key}`);
  }
  return value;
}

export function moneyValue(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === "string" && value.length > 0) {
    return value;
  }
  throw new Error("Missing amount");
}
