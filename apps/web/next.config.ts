import path from "path";

import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

loadEnvConfig(path.resolve(process.cwd(), "..", ".."));

const configuredApiUrl = process.env.API_INTERNAL_URL?.trim();
if (process.env.VERCEL === "1" && !configuredApiUrl) {
  throw new Error(
    "API_INTERNAL_URL must be set for a Vercel build. Use the public Render HTTPS URL.",
  );
}
if (process.env.VERCEL === "1" && configuredApiUrl && /localhost|127\.0\.0\.1/.test(configuredApiUrl)) {
  throw new Error("API_INTERNAL_URL must not point at localhost on Vercel.");
}

const apiInternalUrl = configuredApiUrl || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  agentRules: false,
  allowedDevOrigins: ["127.0.0.1"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiInternalUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
