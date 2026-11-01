import React from "react";
import type { DerivedTranslationResponse } from "../../lib/api-client";
import { SupportedUiLocale, getActiveUiLocale, translate } from "../../lib/i18n";
import { Button } from "../Button";

export interface TranslatedContentProps {
  translation: DerivedTranslationResponse | null;
  isShowingTranslation: boolean;
  errorMessage?: string | null;
  uiLocale?: SupportedUiLocale;
  onShowOriginal: () => void;
  onRetry?: () => void;
}

export function TranslatedContent({
  translation,
  isShowingTranslation,
  errorMessage = null,
  uiLocale,
  onShowOriginal,
  onRetry,
}: TranslatedContentProps) {
  const currentUi = uiLocale ?? getActiveUiLocale();

  if (errorMessage) {
    return (
      <div
        role="alert"
        className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-200"
      >
        <span>{errorMessage}</span>
        {onRetry ? (
          <Button variant="outline" onClick={onRetry}>
            {translate("translations.retryButton", undefined, currentUi)}
          </Button>
        ) : null}
      </div>
    );
  }

  if (!translation || !isShowingTranslation) {
    return null;
  }

  const headerLabel = translation.is_source_language_uncertain
    ? translate(
        "translations.translatedFromUncertain",
        { target: translation.target_locale_label },
        currentUi
      )
    : translate(
        "translations.translatedFromKnown",
        {
          source: translation.source_language_label,
          target: translation.target_locale_label,
        },
        currentUi
      );

  return (
    <section
      aria-label="Derived content translation"
      dir={translation.direction}
      className="mt-3 space-y-2 rounded-xl border border-indigo-200 bg-indigo-50/50 p-4 dark:border-indigo-900/60 dark:bg-indigo-950/30"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-indigo-100 pb-2 text-xs dark:border-indigo-900">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-indigo-900 dark:text-indigo-200">
            {headerLabel}
          </span>
          {translation.is_mock_provider ? (
            <span className="rounded bg-amber-200 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-900">
              {translate("translations.mockPreviewBadge", undefined, currentUi)}
            </span>
          ) : null}
        </div>

        <button
          type="button"
          onClick={onShowOriginal}
          className="font-semibold text-indigo-700 underline hover:text-indigo-900 dark:text-indigo-300"
        >
          {translate("translations.showOriginalButton", undefined, currentUi)}
        </button>
      </div>

      {translation.translated_title ? (
        <h3 className="text-base font-bold text-slate-900 dark:text-white">
          {translation.translated_title}
        </h3>
      ) : null}

      <p className="whitespace-pre-line text-sm leading-relaxed text-slate-800 dark:text-slate-200">
        {translation.translated_body}
      </p>

      <p className="text-[11px] text-slate-500 dark:text-slate-400">
        {translate("translations.originalPreservedNotice", undefined, currentUi)}
      </p>
    </section>
  );
}
