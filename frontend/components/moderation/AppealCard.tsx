import React from "react";
import type { AppealResponse } from "../../lib/api-client";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface AppealCardProps {
  appeal: AppealResponse;
  isModeratorView?: boolean;
  reviewNote: string;
  onReviewNoteChange: (note: string) => void;
  onDecide?: (appealId: string, decision: "accepted" | "rejected") => void;
}

export function AppealCard({
  appeal,
  isModeratorView = false,
  reviewNote,
  onReviewNoteChange,
  onDecide,
}: AppealCardProps) {
  return (
    <article className="space-y-3 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="font-mono font-semibold text-slate-600 dark:text-slate-400">
          Appeal #{appeal.id.slice(0, 8)} • Action: {appeal.original_action_type} ({appeal.original_reason_code})
        </span>
        <span
          className={`rounded-full px-3 py-0.5 font-bold uppercase ${
            appeal.status === "accepted"
              ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
              : appeal.status === "rejected"
              ? "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200"
              : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200"
          }`}
        >
          {appeal.status}
        </span>
      </div>

      <p className="text-xs text-slate-600 dark:text-slate-400">
        <strong>Original Explanation:</strong> {appeal.public_explanation}
      </p>

      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-800 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200">
        <strong>Appellant Statement:</strong> {appeal.appeal_statement}
      </div>

      {appeal.review_decision_note ? (
        <p className="text-xs font-medium text-indigo-700 dark:text-indigo-300">
          <strong>Reviewer Decision ({appeal.decision_reason_code}):</strong> {appeal.review_decision_note}
        </p>
      ) : null}

      {isModeratorView && appeal.status === "pending" ? (
        appeal.can_viewer_decide ? (
          <div className="space-y-2 border-t border-slate-100 pt-3 dark:border-slate-800">
            <input
              type="text"
              value={reviewNote}
              onChange={(e) => onReviewNoteChange(e.target.value)}
              placeholder="Enter required decision rationale (min 5 chars)..."
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
            />
            <div className="flex gap-2">
              <Button
                onClick={() => onDecide && onDecide(appeal.id, "accepted")}
                disabled={reviewNote.trim().length < 5}
              >
                Accept Appeal & Restore
              </Button>
              <Button
                variant="secondary"
                onClick={() => onDecide && onDecide(appeal.id, "rejected")}
                disabled={reviewNote.trim().length < 5}
              >
                Reject Appeal
              </Button>
            </div>
          </div>
        ) : (
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-xs font-medium text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
            {translate("moderation.separationOfDutiesNotice")}
          </div>
        )
      ) : null}
    </article>
  );
}
