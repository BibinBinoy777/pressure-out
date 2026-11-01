import React from "react";
import {
  SUPPORTED_UI_LOCALES,
  SupportedUiLocale,
  getActiveUiLocale,
  translate,
} from "../../lib/i18n";
import { Button } from "../Button";

export interface TranslateContentButtonProps {
  sourceLanguage: string;
  targetLocale?: SupportedUiLocale;
  isLoading?: boolean;
  isShowingTranslation?: boolean;
  uiLocale?: SupportedUiLocale;
  onTargetLocaleChange?: (locale: SupportedUiLocale) => void;
  onRequestTranslation: (targetLocale: SupportedUiLocale) => void;
  onToggleOriginal: () => void;
}

export function TranslateContentButton({
  sourceLanguage,
  targetLocale,
  isLoading = false,
  isShowingTranslation = false,
  uiLocale,
  onTargetLocaleChange,
  onRequestTranslation,
  onToggleOriginal,
}: TranslateContentButtonProps) {
  const currentUi = uiLocale ?? getActiveUiLocale();
  const effectiveTarget: SupportedUiLocale =
    targetLocale ?? (sourceLanguage === currentUi ? "en" : currentUi);
  const targetMeta =
    SUPPORTED_UI_LOCALES.find((l) => l.code === effectiveTarget) ??
    SUPPORTED_UI_LOCALES[0]!;

  return (
    <div className="inline-flex flex-wrap items-center gap-1.5 text-xs">
      <select
        aria-label="Target translation language"
        value={effectiveTarget}
        onChange={(e) =>
          onTargetLocaleChange &&
          onTargetLocaleChange(e.target.value as SupportedUiLocale)
        }
        className="rounded border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
      >
        {SUPPORTED_UI_LOCALES.map((l) => (
          <option key={l.code} value={l.code}>
            {l.nativeName}
          </option>
        ))}
      </select>

      {isShowingTranslation ? (
        <Button variant="outline" onClick={onToggleOriginal}>
          {translate("translations.showOriginalButton", undefined, currentUi)}
        </Button>
      ) : (
        <Button
          variant="outline"
          disabled={isLoading}
          onClick={() => onRequestTranslation(effectiveTarget)}
        >
          {isLoading
            ? translate("translations.translatingStatus", undefined, currentUi)
            : translate(
                "translations.translateButton",
                { locale: targetMeta.nativeName },
                currentUi
              )}
        </Button>
      )}
    </div>
  );
}
