"use client";

import React, { useState } from "react";
import { Container } from "../../../components/Container";
import { FormField } from "../../../components/FormField";
import { Button } from "../../../components/Button";
import type { ExperienceBand } from "../../../lib/api-client";
import { translate } from "../../../lib/i18n";

export default function ProfileSettingsPage() {
  const [displayName, setDisplayName] = useState<string>("");
  const [bio, setBio] = useState<string>("");
  const [roleTitle, setRoleTitle] = useState<string>("");
  const [industry, setIndustry] = useState<string>("");
  const [experienceBand, setExperienceBand] = useState<ExperienceBand>("mid_3_6");
  const [regionLabel, setRegionLabel] = useState<string>("");
  const [isEnabled, setIsEnabled] = useState<boolean>(true);

  return (
    <Container className="max-w-2xl space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
          {translate("settings.profileTitle")}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {translate("settings.professionalDescription")}
        </p>
      </div>

      <form className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <FormField id="prof-display-name" label={translate("settings.displayNameLabel")}>
          <input
            id="prof-display-name"
            type="text"
            maxLength={64}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
        </FormField>

        <FormField id="prof-bio" label={translate("settings.bioLabel")}>
          <textarea
            id="prof-bio"
            rows={3}
            maxLength={500}
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
        </FormField>

        <div className="space-y-4 border-t border-slate-200 pt-6 dark:border-slate-800">
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">
            {translate("settings.professionalHeading")}
          </h2>

          <FormField id="prof-role" label={translate("settings.roleTitleLabel")}>
            <input
              id="prof-role"
              type="text"
              value={roleTitle}
              onChange={(e) => setRoleTitle(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </FormField>

          <FormField id="prof-industry" label={translate("settings.industryLabel")}>
            <input
              id="prof-industry"
              type="text"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </FormField>

          <FormField id="prof-exp" label={translate("settings.experienceBandLabel")}>
            <select
              id="prof-exp"
              value={experienceBand}
              onChange={(e) => setExperienceBand(e.target.value as ExperienceBand)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            >
              <option value="fresher_0_1">0–1 years (Fresher)</option>
              <option value="junior_1_3">1–3 years</option>
              <option value="mid_3_6">3–6 years</option>
              <option value="senior_6_10">6–10 years</option>
              <option value="lead_10_plus">10+ years</option>
            </select>
          </FormField>

          <FormField id="prof-region" label={translate("settings.regionLabel")}>
            <input
              id="prof-region"
              type="text"
              value={regionLabel}
              onChange={(e) => setRegionLabel(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </FormField>

          <label className="flex items-center gap-2 text-sm text-slate-800 dark:text-slate-200">
            <input
              type="checkbox"
              checked={isEnabled}
              onChange={(e) => setIsEnabled(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-indigo-600"
            />
            <span>{translate("settings.enableProfessionalLabel")}</span>
          </label>
        </div>

        <Button type="submit">{translate("settings.saveProfileButton")}</Button>
      </form>
    </Container>
  );
}
