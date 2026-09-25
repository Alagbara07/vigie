import { DEMO_BUSINESS_SLUG } from "@/lib/demo";
import { apiGet, isRecord, MissingBusinessError, requiredString } from "@/lib/api/client";

export type BusinessRecord = {
  id: string;
  name: string;
  slug: string;
  timezone: string;
  default_currency: string;
};

export async function loadDemoBusiness(): Promise<BusinessRecord> {
  const businesses = await apiGet("/api/businesses", parseBusinessList);
  const business = businesses.find((item) => item.slug === DEMO_BUSINESS_SLUG);
  if (!business) {
    throw new MissingBusinessError();
  }
  return business;
}

export function parseBusinessList(value: unknown): BusinessRecord[] {
  if (!Array.isArray(value)) {
    throw new Error("Expected a business list");
  }
  return value.map((item) => {
    if (!isRecord(item)) {
      throw new Error("Expected a business");
    }
    return {
      id: requiredString(item, "id"),
      name: requiredString(item, "name"),
      slug: requiredString(item, "slug"),
      timezone: requiredString(item, "timezone"),
      default_currency: requiredString(item, "default_currency"),
    };
  });
}
