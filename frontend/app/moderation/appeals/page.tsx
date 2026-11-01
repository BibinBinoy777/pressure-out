"use client";

import React, { useState } from "react";
import { Container } from "../../../components/Container";
import { AppealCard } from "../../../components/moderation/AppealCard";
import { FormField } from "../../../components/FormField";
import { Button } from "../../../components/Button";
import type { AppealResponse } from "../../../lib/api-client";
import { translate } from "../../../lib/i18n";

const INITIAL_APPEALS: AppealResponse[] = [
  {
    id: "appeal-demo-001",
    moderation_action_id: "act-demo-001",
    target_type: "post",
    target_id: "post-salary-101",
    original_action_type: "remove_content",
    original_reason_code: "confidential_ip",
    public_explanation: "Removed under confidential information policy.",
    appeal_statement:
      "This post only compares general industry salary bands in Kochi and Bengaluru and contains zero proprietary company secrets.",
    status: "pending",
    can_viewer_decide: false,
    created_at: "2026-10-29T12:30:00Z",
    resolved_at: null,
  },
];

export default function ModerationAppealsPage() {
  const [appeals, setAppeals] = useState<AppealResponse[]>(INITIAL_APPEALS);
  const [actionIdInput, setActionIdInput] = useState<string>("");
  const [statementInput, setStatementInput] = useState<string>("");
  const [reviewNote, setReviewNote] = useState<string>("");

  return (
    <Container className="space-y-8">
      <header className="space-y-2 border-b border-slate-200 pb-5 dark:border-slate-800">
        <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white">
          {translate("moderation.appealsPageTitle")}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {translate("moderation.appealsPageSubtitle")}
        </p>
      </header>

      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h2 className="text-base font-bold text-slate-900 dark:text-white">
          Submit a New Moderation Appeal
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id="appeal-action-id" label="Moderation Action ID">
            <input
              id="appeal-action-id"
              type="text"
              value={actionIdInput}
              onChange={(e) => setActionIdInput(e.target.value)}
              placeholder="e.g., act-demo-002"
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
            />
          </FormField>
          <FormField
            id="appeal-statement"
            label={`Appeal Explanation (${statementInput.length}/2000)`}
          >
            <input
              id="appeal-statement"
              type="text"
              maxLength={2000}
              value={statementInput}
              onChange={(e) => setStatementInput(e.target.value)}
              placeholder="Explain why the content complies with Pressure Out community rules..."
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
            />
          </FormField>
        </div>
        <Button
          disabled={actionIdInput.trim().length < 3 || statementInput.trim().length < 10}
          onClick={() => {
            setAppeals((prev) => [
              ...prev,
              {
                id: "appeal-new-002",
                moderation_action_id: actionIdInput.trim(),
                target_type: "post",
                target_id: "post-user-02",
                original_action_type: "restrict_visibility",
                original_reason_code: "other",
                public_explanation: "Restricted pending review.",
                appeal_statement: statementInput.trim(),
                status: "pending",
                can_viewer_decide: false,
                created_at: new Date().toISOString(),
              },
            ]);
            setActionIdInput("");
            setStatementInput("");
          }}
        >
          Submit Appeal
        </Button>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-bold text-slate-900 dark:text-white">
          Appeal History & Independent Reviewer Queue
        </h2>
        {appeals.map((ap) => (
          <AppealCard
            key={ap.id}
            appeal={ap}
            isModeratorView={true}
            reviewNote={reviewNote}
            onReviewNoteChange={setReviewNote}
          />
        ))}
      </section>
    </Container>
  );
}
