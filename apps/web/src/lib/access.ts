export function canApprove(role: string | null | undefined): boolean {
  return role === "owner" || role === "admin" || role === "member";
}

export function canManageIntegrations(role: string | null | undefined): boolean {
  return role === "owner" || role === "admin";
}
