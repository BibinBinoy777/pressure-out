import React from "react";
import { Container } from "../../../components/Container";
import { AuditEventTable } from "../../../components/moderation/AuditEventTable";
import type { AuditEventResponse } from "../../../lib/api-client";
import { translate } from "../../../lib/i18n";

const SAMPLE_AUDIT_EVENTS: AuditEventResponse[] = [
  {
    id: "aud-001",
    actor_user_id: null,
    actor_role: "system_auto_hold",
    event_category: "auto_protective_hold",
    action_name: "place_under_review",
    target_type: "post",
    target_id: "post-anon-hold-01",
    reason_code: "auto_velocity_hold",
    redacted_metadata: {
      distinct_reporters: 3,
      window_minutes: 30,
      community_slug: "workplace-rants",
    },
    correlation_id: "req_auto_hold_01",
    created_at: "2026-10-29T12:00:00Z",
  },
  {
    id: "aud-002",
    actor_user_id: "mod-reviewer-2",
    actor_role: "global_moderator",
    event_category: "appeal_review",
    action_name: "appeal_accepted",
    target_type: "post",
    target_id: "post-salary-101",
    reason_code: "appeal_overturned",
    redacted_metadata: {
      appeal_id: "appeal-demo-001",
      decision: "accepted",
    },
    correlation_id: "req_appeal_02",
    created_at: "2026-10-29T12:45:00Z",
  },
];

export default function ModerationAuditPage() {
  return (
    <Container className="space-y-6">
      <header className="space-y-2 border-b border-slate-200 pb-5 dark:border-slate-800">
        <span className="inline-block rounded-full bg-slate-900 px-3 py-1 text-xs font-bold uppercase text-white dark:bg-slate-100 dark:text-slate-900">
          Admin-Only • Read-Only Append-Only Ledger
        </span>
        <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white">
          {translate("moderation.auditPageTitle")}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {translate("moderation.auditPageSubtitle")}
        </p>
      </header>

      <AuditEventTable events={SAMPLE_AUDIT_EVENTS} />
    </Container>
  );
}
