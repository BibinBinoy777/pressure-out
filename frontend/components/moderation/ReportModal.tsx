import React from "react";
import type { ReportReasonCode, ReportTargetType } from "../../lib/api-client";
import { FormField } from "../FormField";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface ReportModalProps {
  isOpen: boolean;
  targetType: ReportTargetType;
  targetId: string;
  selectedReason: ReportReasonCode;
  details: string;
  isSubmitting?: boolean;
  isSubmitted?: boolean;
  errorMessage?: string | null;
  onReasonChange: (reason: ReportReasonCode) => void;
  onDetailsChange: (details: string) => void;
  onSubmit: () => void;
  onClose: () => void;
}

const REASONS: ReportReasonCode[] = [
  "doxxing_pii",
  "threat",
  "harassment",
  "impersonation",
  "hate_speech",
  "confidential_ip",
  "spam",
  "misleading_allegation",
  "other",
];

export function ReportModal({
  isOpen,
  targetType,
  targetId,
  selectedReason,
  details,
  isSubmitting = false,
  isSubmitted = false,
  errorMessage = null,
  onReasonChange,
  onDetailsChange,
  onSubmit,
  onClose,
}: ReportModalProps) {
  if (!isOpen) return null;

  const isHighSeverity =
    selectedReason === "doxxing_pii" || selectedReason === "threat";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="report-modal-heading"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4"
    >
      <div className="w-full max-w-lg space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2
              id="report-modal-heading"
              className="text-lg font-bold text-slate-900 dark:text-white"
            >
              {translate("moderation.reportModalTitle")}
            </h2>
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
              {translate("moderation.reportModalSubtitle")}
            </p>
          </div>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>

        <div className="rounded-lg bg-slate-100 px-3 py-1.5 font-mono text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-300">
          Target: {targetType} #{targetId.slice(0, 12)}
        </div>

        {isSubmitted ? (
          <div
            role="status"
            className="rounded-xl border border-emerald-300 bg-emerald-50 p-4 text-sm font-medium text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200"
          >
            {translate("moderation.submittedConfirmation")}
          </div>
        ) : (
          <div className="space-y-4">
            {errorMessage ? (
              <div
                role="alert"
                className="rounded-lg border border-rose-300 bg-rose-50 p-3 text-xs font-semibold text-rose-800 dark:border-rose-800 dark:bg-rose-950/60 dark:text-rose-200"
              >
                {errorMessage}
              </div>
            ) : null}

            <FormField id="report-reason-select" label={translate("moderation.reasonLabel")}>
              <select
                id="report-reason-select"
                value={selectedReason}
                onChange={(e) => onReasonChange(e.target.value as ReportReasonCode)}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
              >
                {REASONS.map((r) => (
                  <option key={r} value={r}>
                    {translate(`moderation.reasons.${r}`)}
                  </option>
                ))}
              </select>
            </FormField>

            {isHighSeverity ? (
              <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
                {translate("moderation.highSeverityVelocityNote")}
              </div>
            ) : null}

            <FormField
              id="report-details-input"
              label={`${translate("moderation.detailsLabel")} (${details.length}/1000)`}
            >
              <textarea
                id="report-details-input"
                rows={3}
                maxLength={1000}
                value={details}
                onChange={(e) => onDetailsChange(e.target.value)}
                placeholder="Provide optional context to help human moderators evaluate this report..."
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
              />
            </FormField>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button onClick={onSubmit} disabled={isSubmitting}>
                {isSubmitting ? "Submitting..." : translate("moderation.submitReportButton")}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
