export class ApiError extends Error {
  readonly status: number | null;
  readonly detail: string | null;

  constructor(status: number | null = null, detail: string | null = null) {
    super("VIGIE can't reach the intelligence service.");
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
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
    response = await fetch(path, { cache: "no-store", credentials: "include" });
  } catch {
    throw new ApiError();
  }
  if (!response.ok) {
    throw new ApiError(response.status, await safeDetail(response));
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
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError();
  }
  if (!response.ok) {
    throw new ApiError(response.status, await safeDetail(response));
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

async function safeDetail(response: Response): Promise<string | null> {
  try {
    const payload: unknown = await response.json();
    if (typeof payload !== "object" || payload === null || !("detail" in payload)) {
      return null;
    }
    const detail = payload.detail;
    if (typeof detail !== "string" || detail.length === 0 || detail.length > 200) {
      return null;
    }
    return detail;
  } catch {
    return null;
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
