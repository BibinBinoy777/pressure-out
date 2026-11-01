/**
 * Unicode NFC normalization and direction/script detection helpers for Pressure Out (Phase 10).
 *
 * Preserves native scripts (English, Malayalam, Hindi, Tamil, Arabic RTL, CJK,
 * Emoji, and mixed-language / code-switched text) without lossy conversion.
 */
export function normalizeUnicodeNfc(input: string): string {
  if (typeof input !== "string") {
    throw new TypeError(`Expected string for Unicode normalization, received ${typeof input}`);
  }
  return input.replace(/\0/g, "").normalize("NFC");
}

export function normalizeOptionalUnicodeNfc(
  input: string | null | undefined
): string | null {
  if (input === null || input === undefined) {
    return null;
  }
  return normalizeUnicodeNfc(input);
}

const RTL_LANG_PREFIXES = ["ar", "he", "fa", "ur"];

/**
 * Determine safe text direction ("ltr" or "rtl") from language metadata and Unicode code points.
 */
export function detectTextDirection(
  text: string,
  languageTag?: string | null
): "ltr" | "rtl" {
  const baseTag = (languageTag || "").trim().toLowerCase().split("-")[0] ?? "";
  if (RTL_LANG_PREFIXES.includes(baseTag)) {
    return "rtl";
  }
  for (let i = 0; i < text.length; i += 1) {
    const cp = text.codePointAt(i) ?? 0;
    if (
      (cp >= 0x0590 && cp <= 0x05ff) ||
      (cp >= 0x0600 && cp <= 0x06ff) ||
      (cp >= 0x0750 && cp <= 0x077f) ||
      (cp >= 0x08a0 && cp <= 0x08ff)
    ) {
      return "rtl";
    }
  }
  return "ltr";
}

export function formatLanguageBadgeLabel(languageTag?: string | null): string {
  const clean = (languageTag || "und").trim().toLowerCase();
  const labels: Record<string, string> = {
    en: "English (en)",
    ml: "മലയാളം (ml)",
    hi: "हिन्दी (hi)",
    ta: "தமிழ் (ta)",
    es: "Español (es)",
    ar: "العربية (ar)",
    mul: "Mixed / Code-Switched (mul)",
    und: "Undetermined (und)",
  };
  return labels[clean] ?? clean.toUpperCase();
}
