"use client";

import React, { useState } from "react";
import { Container } from "../../../components/Container";
import { ModerationQueueCard } from "../../../components/moderation/ModerationQueueCard";
import type { ModerationQueueItemResponse } from "../../../lib/api-client";
import { translate } from "../../../lib/i18n";

const INITIAL_QUEUE_ITEMS: ModerationQueueItemResponse[] = [
  {
    report_id: "rep-high-vel-001",
    target_type: "post",
    target_id: "post-anon-hold-01",
    community_slug: "workplace-rants",
    content_language: "ml",
    reason_code: "doxxing_pii",
    details: "Flagged for potential personal phone number in post body.",
    priority_score: 10,
    status: "in_review",
    distinct_reporter_count: 3,
    allegation_notice: translate("moderation.allegationBanner"),
    target_preview: {
      target_type: "post",
      target_id: "post-anon-hold-01",
      community_slug: "workplace-rants",
      content_language: "ml",
      moderation_status: "awaiting_review",
      is_protective_hold: true,
      title: "വെള്ളിയാഴ്ച വൈകുന്നേരം അമിത ജോലിഭാരം",
      body_excerpt: "ആഴ്ചാവസാനം വിശ്രമമില്ലാതെ പണിയെടുപ്പിക്കുന്നു.",
      public_author: {
        identity_mode: "anonymous",
        display_name: "Anonymous Member",
        handle: null,
        avatar_url: null,
        professional_badge: null,
        is_anonymous_op: false,
      },
    },
    created_at: "2026-10-29T12:00:00Z",
  },
];

export default function ModerationQueuePage() {
  const [items, setItems] = useState<ModerationQueueItemResponse[]>(INITIAL_QUEUE_ITEMS);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [languageFilter, setLanguageFilter] = useState<string>("all");
  const [highSeverityOnly, setHighSeverityOnly] = useState<boolean>(false);
  const [selectedReason, setSelectedReason] = useState<string>("doxxing_pii");
  const [publicExplanation, setPublicExplanation] = useState<string>(
    "Reviewed by community moderation team."
  );
  const [internalNote, setInternalNote] = useState<string>(
    "Verified against Pressure Out privacy policy."
  );

  const visibleItems = items.filter((it) => {
    if (statusFilter !== "all" && it.status !== statusFilter) return false;
    if (languageFilter !== "all" && it.content_language !== languageFilter) return false;
    if (highSeverityOnly && it.priority_score < 10) return false;
    return true;
  });

  return (
    <Container className="space-y-6">
      <header className="space-y-2 border-b border-slate-200 pb-5 dark:border-slate-800">
        <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white">
          {translate("moderation.queuePageTitle")}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {translate("moderation.queuePageSubtitle")}
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 text-xs dark:border-slate-800 dark:bg-slate-900">
        <label className="flex items-center gap-1.5 font-semibold">
          Status:
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="all">All Active</option>
            <option value="open">Open</option>
            <option value="in_review">In Review (Protective Hold)</option>
            <option value="escalated_language_specialist">
              Escalated (Language Specialist)
            </option>
          </select>
        </label>

        <label className="flex items-center gap-1.5 font-semibold">
          Language:
          <select
            value={languageFilter}
            onChange={(e) => setLanguageFilter(e.target.value)}
            className="rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="all">All Languages</option>
            <option value="en">English (en)</option>
            <option value="ml">Malayalam (ml)</option>
            <option value="hi">Hindi (hi)</option>
            <option value="ta">Tamil (ta)</option>
          </select>
        </label>

        <label className="flex items-center gap-1.5 font-semibold">
          <input
            type="checkbox"
            checked={highSeverityOnly}
            onChange={(e) => setHighSeverityOnly(e.target.checked)}
          />
          High-Severity Only (P10 Doxxing/Threats)
        </label>
      </div>

      {visibleItems.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          No reports match the current filters.
        </p>
      ) : (
        <div className="space-y-4">
          {visibleItems.map((item) => (
            <ModerationQueueCard
              key={item.report_id}
              item={item}
              selectedActionReason={selectedActionReason(selectedReason)}
              publicExplanation={publicExplanation}
              internalNote={internalNote}
              onReasonChange={setSelectedReason}
              onPublicExplanationChange={setPublicExplanation}
              onInternalNoteChange={setInternalNote}
              onExecuteAction={() =>
                setItems((prev) =>
                  prev.filter((x) => x.report_id !== item.report_id)
                )
              }
            />
          ))}
        </div>
      )}
    </Container>
  );
}

function selectedActionReason(val: string): string {
  return val;
}
