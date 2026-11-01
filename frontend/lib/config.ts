/**
 * Environment-aware configuration for the Pressure Out Next.js frontend.
 *
 * Distinguishes between:
 * - Browser-accessible backend URLs (`NEXT_PUBLIC_API_BASE_URL`)
 * - Container-internal SSR backend URLs (`INTERNAL_API_BASE_URL`)
 * Never embeds server-only secrets into client bundles.
 */
export interface FrontendConfig {
  readonly apiBaseUrl: string;
  readonly defaultLocale: string;
  readonly requestTimeoutMs: number;
}

export function resolveApiBaseUrl(isServerRuntime: boolean = typeof window === "undefined"): string {
  if (isServerRuntime && process.env.INTERNAL_API_BASE_URL) {
    return process.env.INTERNAL_API_BASE_URL.replace(/\/+$/, "");
  }
  const publicUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  return publicUrl.replace(/\/+$/, "");
}

export function getFrontendConfig(): FrontendConfig {
  return {
    apiBaseUrl: resolveApiBaseUrl(),
    defaultLocale: process.env.NEXT_PUBLIC_DEFAULT_LOCALE || "en",
    requestTimeoutMs: 5000,
  };
}
