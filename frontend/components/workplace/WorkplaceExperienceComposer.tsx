"use client";

import React, { useState } from "react";
import type { IdentityMode } from "../../lib/api-client";
import { IdentityModeSelector } from "../identity/IdentityModeSelector";
import { FormField } from "../FormField";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface WorkplaceExperienceComposerProps {
  onPublish?: (payload: Record<string, unknown>) => void;
}

const EXPERIENCE_CATEGORIES = [
  { value: "workplace_culture", label: "Workplace Culture" },
  { value: "management", label: "Management & Leadership" },
  { value: "career_growth", label: "Career Growth" },
  { value: "compensation", label: "Compensation & Transparency" },
  { value: "work_life_balance", label: "Work-Life Balance" },
  { value: "workplace_conflict", label: "Workplace Conflict" },
  { value: "remote_work", label: "Remote & Hybrid Work" },
  { value: "team_experience", label: "Team Experience" },
  { value: "career_change", label: "Career Change" },
  { value: "job_search", label: "Job Search Experience" },
  { value: "other", label: "Other" },
];

export function WorkplaceExperienceComposer({
  onPublish,
}: WorkplaceExperienceComposerProps) {
  const [category, setCategory] = useState<string>("workplace_culture");
  const [identityMode, setIdentityMode] = useState<IdentityMode>("pseudonymous");
  const [language, setLanguage] = useState<string>("en");
  const [title, setTitle] = useState<string>("");
  const [body, setBody] = useState<string>("");
  const [lessonLearned, setLessonLearned] = useState<string>("");
  const [published, setPublished] = useState<boolean>(false);

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-900 dark:text-white">
          Share a Workplace Experience
        </h2>
        <span className="rounded-full bg-slate-100 px-3 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {translate("workplace.selfReportedBadge")}
        </span>
      </div>

      <p className="rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
        {translate("workplace.safetyReminder")}
      </p>

      {published ? (
        <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-xs font-semibold text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200">
          Workplace experience published using canonical post lifecycle!
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="wx-category-select" label="Experience Category">
          <select
            id="wx-category-select"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          >
            {EXPERIENCE_CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </FormField>

        <FormField id="wx-lang-select" label={translate("posts.languageLabel")}>
          <select
            id="wx-lang-select"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          >
            <option value="en">English (en)</option>
            <option value="ml">Malayalam — മലയാളം (ml)</option>
            <option value="hi">Hindi — हिन्दी (hi)</option>
            <option value="ta">Tamil — தமிழ் (ta)</option>
            <option value="es">Spanish — Español (es)</option>
            <option value="mul">Mixed / Code-Switched (mul)</option>
          </select>
        </FormField>
      </div>

      <IdentityModeSelector value={identityMode} onChange={setIdentityMode} />

      <FormField id="wx-title-input" label={translate("posts.titleLabel")}>
        <input
          id="wx-title-input"
          type="text"
          maxLength={220}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Summarize your workplace experience..."
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
      </FormField>

      <FormField id="wx-body-input" label={translate("posts.bodyLabel")}>
        <textarea
          id="wx-body-input"
          rows={3}
          maxLength={15000}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Share what happened, how it affected your work, and how you navigated it..."
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
      </FormField>

      <FormField
        id="wx-lesson-input"
        label="Key Takeaway or Lesson Learned (Optional, max 500 chars)"
      >
        <input
          id="wx-lesson-input"
          type="text"
          maxLength={500}
          value={lessonLearned}
          onChange={(e) => setLessonLearned(e.target.value)}
          placeholder="Optional takeaway for peers facing a similar workplace situation..."
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
      </FormField>

      <Button
        disabled={title.trim().length < 3 || body.trim().length < 1}
        onClick={() => {
          setPublished(true);
          if (onPublish) {
            onPublish({ category, identityMode, language, title, body, lessonLearned });
          }
        }}
      >
        {translate("posts.publishButton")}
      </Button>
    </section>
  );
}
