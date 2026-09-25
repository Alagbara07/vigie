export function greetingFor(now: Date, timeZone: string): string {
  const hour = Number(
    new Intl.DateTimeFormat("en-GB", {
      hour: "numeric",
      hourCycle: "h23",
      timeZone,
    }).format(now),
  );
  if (hour < 12) {
    return "Good morning";
  }
  if (hour < 17) {
    return "Good afternoon";
  }
  return "Good evening";
}

export function givenName(businessName: string): string {
  const [first] = businessName.trim().split(/\s+/);
  return first || businessName;
}

export function formatMoney(amount: string, currency: string): string {
  const value = Number(amount);
  const formatted = new Intl.NumberFormat("en-NG", {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 2,
  }).format(value);
  if (currency === "NGN") {
    return `₦${formatted}`;
  }
  return `${currency} ${formatted}`;
}

export function formatDate(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone,
  }).format(new Date(iso));
}

export function relativeTime(iso: string, now: Date): string {
  const minutes = Math.round((now.getTime() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) {
    return "Just now";
  }
  if (minutes < 60) {
    return minutes === 1 ? "1 minute ago" : `${minutes} minutes ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return hours === 1 ? "1 hour ago" : `${hours} hours ago`;
  }
  const days = Math.round(hours / 24);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

export function conversationWhen(iso: string, timeZone: string, now: Date): string {
  const current = localParts(now, timeZone);
  const occurred = localParts(new Date(iso), timeZone);
  if (dateKey(occurred) === dateKey(current)) {
    return "Today";
  }
  if (dateKey(occurred) === dateKey(previousDay(current))) {
    return "Yesterday";
  }
  return formatDate(iso, timeZone);
}

export function severityLabel(severity: string): { label: string; tone: "high" | "medium" | "low" } {
  if (severity === "CRITICAL") {
    return { label: "Critical", tone: "high" };
  }
  if (severity === "HIGH") {
    return { label: "High priority", tone: "high" };
  }
  if (severity === "MEDIUM") {
    return { label: "Medium", tone: "medium" };
  }
  if (severity === "INFO") {
    return { label: "Info", tone: "low" };
  }
  return { label: "Low", tone: "low" };
}

type DateParts = { year: number; month: number; day: number };

function localParts(date: Date, timeZone: string): DateParts {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const read = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? "0");
  return { year: read("year"), month: read("month"), day: read("day") };
}

function previousDay(parts: DateParts): DateParts {
  const utc = new Date(Date.UTC(parts.year, parts.month - 1, parts.day));
  utc.setUTCDate(utc.getUTCDate() - 1);
  return { year: utc.getUTCFullYear(), month: utc.getUTCMonth() + 1, day: utc.getUTCDate() };
}

function dateKey(parts: DateParts): string {
  return `${parts.year}-${parts.month}-${parts.day}`;
}
