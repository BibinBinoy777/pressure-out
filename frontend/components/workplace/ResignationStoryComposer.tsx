"use client";

import React, { useState } from "react";
import type { IdentityMode } from "../../lib/api-client";
import { IdentityModeSelector } from "../identity/IdentityModeSelector";
import { FormField } from "../FormField";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface ResignationStoryComposerProps {
  onPublish?: (payload: Record<string, unknown>) => void;
}

const RESIGNATION_REASONS = [
  { value: "better_opportunity", label: "Better Career Opportunity" },
  { value: "compensation", label: "Compensation & Pay Disparity" },
  { value: "management_problems", label: "Management Problems" },
  { value: "workplace_culture", label: "Unhealthy Workplace Culture" },
  { value: "workload", label: "Unsustainable Workload" },
  { value: "work_life_balance", label: "Work-Life Balance" },
  { value: "lack_of_growth", label: "Lack of Career Growth" },
  { value: "role_mismatch", label: "Role Mismatch" },
  { value: "relocation", label: "Relocation" },
  { value: "contract_or_layoff", label: "Contract Ended / Role Eliminated" },
  { value: "career_change", label: "Career or Industry Change" },
  { value: "entrepreneurship", label: "Entrepreneurship / Independent Work" },
  { value: "other", label: "Other" },
];

export function ResignationStoryComposer({
  onPublish,
}: ResignationStoryComposerProps) {
  const [identityMode, setIdentityMode] = useState<IdentityMode>("anonymous");
  const [primaryReason, setPrimaryReason] = useState<string>("better_opportunity");
  const [secondaryReason, setSecondaryReason] = useState<string>("");
  const [experienceBand, setExperienceBand] = useState<string>("mid_3_6");
  const [industryCategory, setIndustryCategory] = useState<string>("technology");
  const [lessonLearned, setLessonLearned] = useState<string>("");
  const [title, setTitle] = useState<string>("");
  const [body, setBody] = useState<string>("");
  const [published, setPublished] = useState<boolean>(false);

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-900 dark:text-white">
          Share a Resignation Story
        </h2>
        <span className="rounded-full bg-indigo-50 px-3 py-0.5 text-xs font-semibold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
          c/resignation-stories • {translate("workplace.selfReportedBadge")}
        </span>
      </div>

      <p className="rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
        {translate("workplace.safetyReminder")}
      </p>

      {published ? (
        <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-xs font-semibold text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200">
          Resignation story published! Note: Narrative stories are never automatically extracted into aggregated metrics.
        </div>
      ) : null}

      <IdentityModeSelector value={identityMode} onChange={setIdentityMode} />

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="resign-primary-reason" label="Primary Reason for Leaving (Optional)">
          <select
            id="resign-primary-reason"
            value={primaryReason}
            onChange={(e) => setPrimaryReason(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          >
            {RESIGNATION_REASONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </FormField>

        <FormField id="resign-secondary-reason" label="Secondary Reason (Optional)">
          <select
            id="resign-secondary-reason"
            value={secondaryReason}
            onChange={(e) => setSecondaryReason(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          >
            <option value="">None</option>
            {RESIGNATION_REASONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </FormField>

        <FormField id="resign-exp-band" label="General Experience Band (Optional)">
          <select
            id="resign-exp-band"
            value={experienceBand}
            onChange={(e) => setExperienceBand(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          >
            <option value="fresher_0_1">0–1 years (Fresher)</option>
            <option value="junior_1_3">1–3 years (Junior)</option>
            <option value="mid_3_6">3–6 years (Mid-Level)</option>
            <option value="senior_6_10">6–10 years (Senior)</option>
            <option value="lead_10_plus">10+ years (Lead / Principal)</option>
          </select>
        </FormField>

        <FormField id="resign-industry" label="Broad Industry Category (Optional)">
          <select
            id="resign-industry"
            value={industryCategory}
            onChange={(e) => setIndustryCategory(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          >
            <option value="technology">Technology & Software</option>
            <option value="finance">Finance & Banking</option>
            <option value="healthcare">Healthcare</option>
            <option value="education">Education</option>
            <option value="consulting_services">Consulting & Services</option>
            <option value="other">Other</option>
          </select>
        </FormField>
      </div>

      <FormField id="resign-title" label={translate("posts.titleLabel")}>
        <input
          id="resign-title"
          type="text"
          maxLength={220}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Why I finally handed in my notice..."
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
      </FormField>

      <FormField id="resign-body" label="Your Resignation Story">
        <textarea
          id="resign-body"
          rows={3}
          maxLength={15000}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Share what led to your decision, how the transition went, and what changed afterward..."
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
      </FormField>

      <FormField id="resign-lesson" label="Lesson Learned After Leaving (Optional)">
        <input
          id="resign-lesson"
          type="text"
          maxLength={500}
          value={lessonLearned}
          onChange={(e) => setLessonLearned(e.target.value)}
          placeholder="What advice would you give someone in the same shoes?"
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
      </FormField>

      <Button
        disabled={title.trim().length < 3 || body.trim().length < 1}
        onClick={() => {
          setPublished(true);
          if (onPublish) {
            onPublish({
              identityMode,
              primaryReason,
              secondaryReason,
              experienceBand,
              industryCategory,
              lessonLearned,
              title,
              body,
            });
          }
        }}
      >
        Publish Resignation Story
      </Button>
    </section>
  );
}
