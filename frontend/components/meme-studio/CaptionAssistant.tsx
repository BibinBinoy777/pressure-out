import React from "react";
import type { CaptionSuggestionItem } from "../../lib/api-client";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface CaptionAssistantProps {
  prompt: string;
  tone: string;
  suggestions: CaptionSuggestionItem[];
  quotaRemaining: number | null;
  dailyLimit: number;
  isMockProvider: boolean;
  aiEnabled: boolean;
  isLoading?: boolean;
  onPromptChange: (prompt: string) => void;
  onToneChange: (tone: string) => void;
  onGenerateSuggestions: () => void;
  onApplySuggestion: (item: CaptionSuggestionItem) => void;
}

const TONES = ["sarcastic", "wholesome", "dramatic", "absurd", "deadpan"];

export function CaptionAssistant({
  prompt,
  tone,
  suggestions,
  quotaRemaining,
  dailyLimit,
  isMockProvider,
  aiEnabled,
  isLoading = false,
  onPromptChange,
  onToneChange,
  onGenerateSuggestions,
  onApplySuggestion,
}: CaptionAssistantProps) {
  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            {translate("memeStudio.captionAssistantHeading")}
          </h2>
          <p className="text-xs text-slate-600 dark:text-slate-400">
            {translate("memeStudio.captionAssistantSubtitle")}
          </p>
        </div>
        {quotaRemaining !== null ? (
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            Quota: {quotaRemaining}/{dailyLimit} remaining today
          </span>
        ) : null}
      </div>

      {isMockProvider ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-200">
          {translate("memeStudio.mockDisclosureBanner")}
        </div>
      ) : null}

      {!aiEnabled ? (
        <p className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
          {translate("memeStudio.aiDisabledBanner")}
        </p>
      ) : (
        <div className="space-y-3">
          <div>
            <label htmlFor="ai-caption-prompt" className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
              {translate("memeStudio.scenarioPromptLabel")} ({prompt.length}/400)
            </label>
            <textarea
              id="ai-caption-prompt"
              rows={2}
              maxLength={400}
              value={prompt}
              onChange={(e) => onPromptChange(e.target.value)}
              placeholder={translate("memeStudio.scenarioPromptPlaceholder")}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs font-medium text-slate-600 dark:text-slate-400">
                {translate("memeStudio.toneLabel")}:
              </span>
              {TONES.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => onToneChange(t)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium capitalize ${
                    tone === t
                      ? "bg-indigo-600 text-white"
                      : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>

            <Button
              variant="secondary"
              onClick={onGenerateSuggestions}
              disabled={isLoading || prompt.trim().length < 3}
            >
              {isLoading ? "Generating..." : translate("memeStudio.suggestCaptionsButton")}
            </Button>
          </div>

          {suggestions.length > 0 ? (
            <div className="grid gap-2.5 pt-2 sm:grid-cols-2">
              {suggestions.map((s, idx) => (
                <div
                  key={`${s.top_text}-${idx}`}
                  className="flex flex-col justify-between rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs dark:border-slate-800 dark:bg-slate-950"
                >
                  <div className="space-y-1">
                    <p className="font-semibold text-slate-900 dark:text-white">
                      Top: {s.top_text}
                    </p>
                    <p className="font-semibold text-indigo-700 dark:text-indigo-300">
                      Bottom: {s.bottom_text}
                    </p>
                  </div>
                  <div className="mt-2 pt-2">
                    <Button variant="outline" onClick={() => onApplySuggestion(s)}>
                      {translate("memeStudio.applySuggestionButton")}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
