import React from "react";
import type { MemeJobResponse } from "../../lib/api-client";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface GenerationJobStatusProps {
  job: MemeJobResponse | null;
  onCancelJob: (jobId: string) => void;
  onRetryJob: () => void;
}

export function GenerationJobStatus({
  job,
  onCancelJob,
  onRetryJob,
}: GenerationJobStatusProps) {
  if (!job) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="space-y-2 rounded-xl border border-indigo-200 bg-indigo-50/60 p-4 text-xs dark:border-indigo-900 dark:bg-indigo-950/40"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-bold uppercase tracking-wider text-indigo-800 dark:text-indigo-300">
          AI Image Job #{job.id.slice(0, 8)} • Status: {job.status.toUpperCase()}
        </span>
        {job.is_mock_provider ? (
          <span className="rounded bg-amber-200 px-2 py-0.5 font-mono text-[11px] text-amber-900">
            local_mock
          </span>
        ) : null}
      </div>

      <p className="text-slate-700 dark:text-slate-300">
        Prompt: “{job.prompt}” (Attempt {job.attempt_count})
      </p>

      {job.status === "failed" && job.error_message_safe ? (
        <p className="font-semibold text-rose-700 dark:text-rose-400">
          Error ({job.error_code}): {job.error_message_safe}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2 pt-1">
        {job.status === "queued" ? (
          <Button variant="outline" onClick={() => onCancelJob(job.id)}>
            {translate("memeStudio.cancelJobButton")}
          </Button>
        ) : null}
        {job.status === "failed" ? (
          <Button variant="secondary" onClick={onRetryJob}>
            {translate("memeStudio.retryJobButton")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
