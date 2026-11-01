import React from "react";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface ImageGenerationPanelProps {
  prompt: string;
  styleTone: string;
  aiImageEnabled: boolean;
  hasActiveJob: boolean;
  quotaRemaining: number | null;
  dailyLimit: number;
  onStartJob: () => void;
}

export function ImageGenerationPanel({
  prompt,
  styleTone,
  aiImageEnabled,
  hasActiveJob,
  quotaRemaining,
  dailyLimit,
  onStartJob,
}: ImageGenerationPanelProps) {
  return (
    <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-bold text-slate-900 dark:text-white">
            {translate("memeStudio.imageGenHeading")}
          </h2>
          <p className="text-xs text-slate-600 dark:text-slate-400">
            {translate("memeStudio.imageGenSubtitle")}
          </p>
        </div>
        {quotaRemaining !== null ? (
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            Image Jobs: {quotaRemaining}/{dailyLimit} left today
          </span>
        ) : null}
      </div>

      {!aiImageEnabled ? (
        <p className="text-xs text-slate-500">
          {translate("memeStudio.aiDisabledBanner")}
        </p>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <span className="text-xs text-slate-600 dark:text-slate-400">
            Tone: <strong className="capitalize">{styleTone}</strong> • Max 1 concurrent job per account
          </span>
          <Button
            variant="secondary"
            onClick={onStartJob}
            disabled={hasActiveJob || prompt.trim().length < 3}
          >
            {hasActiveJob ? "Job in Progress..." : translate("memeStudio.startImageJobButton")}
          </Button>
        </div>
      )}
    </section>
  );
}
