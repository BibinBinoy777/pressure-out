import React from "react";
import type { ModerationQueueItemResponse } from "../../lib/api-client";
import { AuthorBadge } from "../identity/AuthorBadge";
import { FormField } from "../FormField";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface ModerationQueueCardProps {
  item: ModerationQueueItemResponse;
  selectedActionReason: string;
  publicExplanation: string;
  internalNote: string;
  onReasonChange: (reason: string) => void;
  onPublicExplanationChange: (text: string) => void;
  onInternalNoteChange: (text: string) => void;
  onExecuteAction: (actionType: string) => void;
}

const ACTION_REASONS = [
  "doxxing_pii",
  "threat",
  "harassment",
  "impersonation",
  "hate_speech",
  "confidential_ip",
  "spam",
  "misleading_allegation",
  "no_violation_found",
  "language_specialist_needed",
  "other",
];

export function ModerationQueueCard({
  item,
  selectedActionReason,
  publicExplanation,
  internalNote,
  onReasonChange,
  onPublicExplanationChange,
  onInternalNoteChange,
  onExecuteAction,
}: ModerationQueueCardProps) {
  const preview = item.target_preview;
  const canSubmitAction =
    selectedActionReason.trim().length > 0 &&
    publicExplanation.trim().length >= 3 &&
    internalNote.trim().length >= 3;

  return (
    <article className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span
            className={`rounded-md px-2.5 py-0.5 font-bold uppercase ${
              item.priority_score >= 10
                ? "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200"
                : "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200"
            }`}
          >
            Priority P{item.priority_score}
          </span>
          <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            Reason: {item.reason_code}
          </span>
          <span className="rounded-md border border-slate-300 px-2 py-0.5 font-semibold text-slate-700 dark:border-slate-700 dark:text-slate-300">
            {item.distinct_reporter_count} distinct reporter(s)
          </span>
          <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono uppercase text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            Lang: {item.content_language}
          </span>
          {item.community_slug ? (
            <span className="font-semibold text-indigo-700 dark:text-indigo-300">
              c/{item.community_slug}
            </span>
          ) : null}
        </div>

        <div>
          {preview.is_protective_hold ? (
            <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              {translate("moderation.protectiveHoldBadge")}
            </span>
          ) : item.status === "escalated_language_specialist" ? (
            <span className="rounded-full bg-purple-100 px-3 py-1 text-xs font-bold text-purple-900 dark:bg-purple-950 dark:text-purple-200">
              {translate("moderation.languageEscalatedBadge")}
            </span>
          ) : (
            <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">
              {translate("moderation.openReportBadge")}
            </span>
          )}
        </div>
      </div>

      <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
        {item.allegation_notice}
      </p>

      <div className="space-y-2 rounded-xl border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-950/60">
        {preview.public_author ? (
          <AuthorBadge author={preview.public_author} />
        ) : (
          <span className="text-xs font-semibold text-slate-500">
            Target: {preview.target_type} #{preview.target_id.slice(0, 8)}
          </span>
        )}
        {preview.title ? (
          <h3 className="text-base font-bold text-slate-900 dark:text-white">
            {preview.title}
          </h3>
        ) : null}
        <p className="whitespace-pre-line text-sm text-slate-800 dark:text-slate-200">
          {preview.body_excerpt}
        </p>
      </div>

      {item.details ? (
        <p className="text-xs text-slate-600 dark:text-slate-400">
          <strong>Reporter Context:</strong> {item.details}
        </p>
      ) : null}

      <div className="grid gap-3 border-t border-slate-100 pt-4 sm:grid-cols-3 dark:border-slate-800">
        <FormField
          id={`mod-reason-${item.report_id}`}
          label="Required Policy Decision Reason"
        >
          <select
            id={`mod-reason-${item.report_id}`}
            value={selectedActionReason}
            onChange={(e) => onReasonChange(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          >
            {ACTION_REASONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </FormField>

        <FormField
          id={`mod-pub-exp-${item.report_id}`}
          label="Public Explanation (Sent to Author)"
        >
          <input
            id={`mod-pub-exp-${item.report_id}`}
            type="text"
            value={publicExplanation}
            onChange={(e) => onPublicExplanationChange(e.target.value)}
            placeholder="Clear policy reason and appeal guidance..."
            className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
        </FormField>

        <FormField
          id={`mod-int-note-${item.report_id}`}
          label="Internal Audit Note"
        >
          <input
            id={`mod-int-note-${item.report_id}`}
            type="text"
            value={internalNote}
            onChange={(e) => onInternalNoteChange(e.target.value)}
            placeholder="Moderator rationale for audit trail..."
            className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
        </FormField>
      </div>

      <div className="flex flex-wrap items-center gap-2 pt-2">
        <Button
          variant="outline"
          disabled={!canSubmitAction}
          onClick={() => onExecuteAction("dismiss_reports")}
        >
          Dismiss Report (Keep Published)
        </Button>
        <Button
          variant="outline"
          disabled={!canSubmitAction}
          onClick={() => onExecuteAction("redact_pii")}
        >
          Redact Personal Info
        </Button>
        <Button
          variant="secondary"
          disabled={!canSubmitAction}
          onClick={() => onExecuteAction("restrict_visibility")}
        >
          Restrict Visibility
        </Button>
        <Button
          variant="secondary"
          disabled={!canSubmitAction}
          onClick={() => onExecuteAction("remove_content")}
        >
          Remove Content
        </Button>
        <Button
          variant="outline"
          onClick={() => onExecuteAction("escalate_language_specialist")}
        >
          {translate("moderation.escalateLanguageButton")}
        </Button>
      </div>
    </article>
  );
}
