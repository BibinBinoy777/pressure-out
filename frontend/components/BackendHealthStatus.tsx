"use client";

import React, { useCallback, useEffect, useState } from "react";
import { fetchBackendHealth, type ApiResult, type HealthApiResponse } from "../lib/api-client";
import { translate } from "../lib/i18n";
import { Button } from "./Button";
import { ErrorMessage } from "./ErrorMessage";
import { LoadingState } from "./LoadingState";

export function BackendHealthStatus() {
  const [loading, setLoading] = useState<boolean>(true);
  const [result, setResult] = useState<ApiResult<HealthApiResponse> | null>(null);

  const checkHealth = useCallback(async () => {
    setLoading(true);
    const res = await fetchBackendHealth();
    setResult(res);
    setLoading(false);
  }, []);

  useEffect(() => {
    void checkHealth();
  }, [checkHealth]);

  return (
    <section
      id="system-status-section"
      aria-label={translate("a11y.backendStatusRegion")}
      className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
          {translate("status.heading")}
        </h2>
        <Button variant="outline" onClick={() => void checkHealth()} disabled={loading}>
          {translate("status.retryButton")}
        </Button>
      </div>

      {loading ? (
        <LoadingState label={translate("status.checking")} />
      ) : result && result.ok ? (
        <div
          role="status"
          aria-live="polite"
          className="rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-emerald-950 dark:border-emerald-800/70 dark:bg-emerald-950/40 dark:text-emerald-100"
        >
          <div className="flex items-center gap-2 font-semibold">
            <span
              aria-hidden="true"
              className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-600 dark:bg-emerald-400"
            />
            <span>{translate("status.onlineTitle")}</span>
          </div>
          <p className="mt-1 text-sm text-emerald-800 dark:text-emerald-300">
            {translate("status.onlineDescription", {
              service: result.data.service,
              version: result.data.api_version,
            })}
          </p>
          {result.correlationId ? (
            <p className="mt-1 font-mono text-xs text-emerald-700 dark:text-emerald-400">
              {translate("status.correlationLabel")}: {result.correlationId}
            </p>
          ) : null}
        </div>
      ) : (
        <ErrorMessage
          title={translate("status.offlineTitle")}
          message={
            result && !result.ok
              ? result.error.message
              : translate("status.offlineFallbackMessage")
          }
          correlationId={result && !result.ok ? result.error.correlationId : undefined}
          correlationLabel={translate("status.correlationLabel")}
          retryLabel={translate("status.retryButton")}
          onRetry={() => void checkHealth()}
        />
      )}
    </section>
  );
}
