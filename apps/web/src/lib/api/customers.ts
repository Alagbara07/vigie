import { isRecord, requiredString } from "@/lib/api/client";

export type CustomerBrief = {
  id: string;
  name: string;
  status: string;
  created_at: string;
};

export function parseCustomer(value: unknown): CustomerBrief | null {
  if (value === null) {
    return null;
  }
  if (!isRecord(value)) {
    throw new Error("Expected a customer");
  }
  return {
    id: requiredString(value, "id"),
    name: requiredString(value, "name"),
    status: requiredString(value, "status"),
    created_at: requiredString(value, "created_at"),
  };
}
