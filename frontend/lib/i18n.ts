/**
 * Multi-locale UI localization system for Pressure Out (Phase 10).
 *
 * Supports:
 * - Complete catalogs for English (`en`), Malayalam (`ml`), Hindi (`hi`),
 *   Tamil (`ta`), and Spanish (`es`).
 * - Persistent UI locale selection (separate from content-language feed filters).
 * - Deterministic dot-path lookup with `{placeholder}` interpolation and safe fallback.
 */
import enCommon from "../locales/en/common.json";
import mlCommon from "../locales/ml/common.json";
import hiCommon from "../locales/hi/common.json";
import taCommon from "../locales/ta/common.json";
import esCommon from "../locales/es/common.json";

export type SupportedUiLocale = "en" | "ml" | "hi" | "ta" | "es";
export type LocaleCatalog = typeof enCommon;

export interface UiLocaleMetadata {
  code: SupportedUiLocale;
  nativeName: string;
  englishName: string;
  direction: "ltr" | "rtl";
}

export const SUPPORTED_UI_LOCALES: UiLocaleMetadata[] = [
  { code: "en", nativeName: "English", englishName: "English", direction: "ltr" },
  { code: "ml", nativeName: "മലയാളം", englishName: "Malayalam", direction: "ltr" },
  { code: "hi", nativeName: "हिन्दी", englishName: "Hindi", direction: "ltr" },
  { code: "ta", nativeName: "தமிழ்", englishName: "Tamil", direction: "ltr" },
  { code: "es", nativeName: "Español", englishName: "Spanish", direction: "ltr" },
];

export const CATALOGS: Record<SupportedUiLocale, LocaleCatalog> = {
  en: enCommon,
  ml: mlCommon,
  hi: hiCommon,
  ta: taCommon,
  es: esCommon,
};

let currentUiLocale: SupportedUiLocale = "en";

export function normalizeUiLocale(locale?: string | null): SupportedUiLocale {
  const cleaned = (locale || "en").trim().toLowerCase().split("-")[0] ?? "en";
  if (cleaned === "ml" || cleaned === "hi" || cleaned === "ta" || cleaned === "es") {
    return cleaned;
  }
  return "en";
}

export function getActiveUiLocale(): SupportedUiLocale {
  return currentUiLocale;
}

export function setActiveUiLocale(locale: string): SupportedUiLocale {
  const resolved = normalizeUiLocale(locale);
  currentUiLocale = resolved;
  return resolved;
}

export function getCatalog(locale: string = currentUiLocale): LocaleCatalog {
  const resolved = normalizeUiLocale(locale);
  return CATALOGS[resolved] ?? CATALOGS.en;
}

export function collectLeafKeyPaths(obj: Record<string, unknown>, prefix: string = ""): string[] {
  const keys: string[] = [];
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === "object" && !Array.isArray(v)) {
      keys.push(...collectLeafKeyPaths(v as Record<string, unknown>, path));
    } else {
      keys.push(path);
    }
  }
  return keys.sort();
}

function lookupPathInCatalog(catalog: unknown, keyPath: string): string | undefined {
  const segments = keyPath.split(".");
  let cursor: unknown = catalog;
  for (const segment of segments) {
    if (cursor !== null && typeof cursor === "object" && segment in (cursor as Record<string, unknown>)) {
      cursor = (cursor as Record<string, unknown>)[segment];
    } else {
      return undefined;
    }
  }
  return typeof cursor === "string" ? cursor : undefined;
}

/**
 * Look up a dot-separated translation key (e.g. "hero.headline") from the active
 * or specified locale catalog, falling back to English (`en`) if needed.
 */
export function translate(
  keyPath: string,
  params?: Record<string, string | number>,
  locale?: string
): string {
  const targetLocale = normalizeUiLocale(locale ?? currentUiLocale);
  const primaryCatalog = CATALOGS[targetLocale] ?? CATALOGS.en;
  const rawTemplate =
    lookupPathInCatalog(primaryCatalog, keyPath) ??
    lookupPathInCatalog(CATALOGS.en, keyPath);

  if (typeof rawTemplate !== "string") {
    return keyPath;
  }

  if (!params) {
    return rawTemplate;
  }

  return rawTemplate.replace(/\{([a-zA-Z0-9_]+)\}/g, (_match, tokenName: string) => {
    const val = params[tokenName];
    return val !== undefined ? String(val) : `{${tokenName}}`;
  });
}
