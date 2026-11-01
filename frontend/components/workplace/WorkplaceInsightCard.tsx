import React from "react";
import type { AggregatedRatingMetricCard } from "../../lib/api-client";
import { translate } from "../../lib/i18n";

export interface WorkplaceInsightCardProps {
  metric: AggregatedRatingMetricCard;
}

export function WorkplaceInsightCard({ metric }: WorkplaceInsightCardProps) {
  return (
    <article className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            Threshold: n &ge; {metric.minimum_threshold}
          </span>
          {!metric.insufficient_data && metric.sample_size_band ? (
            <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">
              Sample: {metric.sample_size_band} contributors
            </span>
          ) : (
            <span className="rounded-full bg-amber-100 px-2.5 py-0.5 font-semibold text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              Suppressed (&lt; {metric.minimum_threshold})
            </span>
          )}
        </div>

        <h3 className="text-base font-bold text-slate-900 dark:text-white">
          {metric.label}
        </h3>

        {metric.insufficient_data ? (
          <p className="rounded-lg border border-dashed border-slate-300 p-3 text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400">
            {translate("workplace.insufficientDataMessage")}
          </p>
        ) : (
          <div className="space-y-2 pt-1">
            <div className="flex items-baseline gap-4">
              <div>
                <span className="text-2xl font-extrabold text-indigo-600 dark:text-indigo-400">
                  {metric.average_rating?.toFixed(1)}
                </span>
                <span className="text-xs text-slate-500"> / 5.0 avg</span>
              </div>
              <div className="text-xs text-slate-600 dark:text-slate-400">
                Median: <strong>{metric.median_rating?.toFixed(1)}</strong>
              </div>
            </div>
          </div>
        )}
      </div>

      <p className="mt-3 border-t border-slate-100 pt-2 text-[11px] text-slate-500 dark:border-slate-800">
        {translate("workplace.selfReportedBadge")}
      </p>
    </article>
  );
}
