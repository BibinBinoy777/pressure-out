import React from "react";
import { Button } from "./Button";

export interface ErrorMessageProps {
  title: string;
  message: string;
  correlationId?: string;
  correlationLabel?: string;
  retryLabel?: string;
  onRetry?: () => void;
}

export function ErrorMessage({
  title,
  message,
  correlationId,
  correlationLabel = "Correlation ID",
  retryLabel,
  onRetry,
}: ErrorMessageProps) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-slate-900 dark:border-amber-800/70 dark:bg-amber-950/40 dark:text-amber-100"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-amber-900 dark:text-amber-200">
            {title}
          </h3>
          <p className="text-sm text-amber-800 dark:text-amber-300">{message}</p>
          {correlationId ? (
            <p className="font-mono text-xs text-amber-700 dark:text-amber-400">
              {correlationLabel}: {correlationId}
            </p>
          ) : null}
        </div>
        {onRetry && retryLabel ? (
          <div className="shrink-0">
            <Button variant="outline" onClick={onRetry}>
              {retryLabel}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
