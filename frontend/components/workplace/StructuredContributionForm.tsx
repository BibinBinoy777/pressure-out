"use client";

import React, { useState } from "react";
import { FormField } from "../FormField";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export function StructuredContributionForm() {
  const [consent, setConsent] = useState<boolean>(true);
  const [industry, setIndustry] = useState<string>("technology");
  const [roleFamily, setRoleFamily] = useState<string>("software_engineering");
  const [experienceBand, setExperienceBand] = useState<string>("mid_3_6");
  const [workArrangement, setWorkArrangement] = useState<string>("hybrid");
  const [overallSatisfaction, setOverallSatisfaction] = useState<number>(4);
  const [workLifeBalance, setWorkLifeBalance] = useState<number>(4);
  const [managementSupport, setManagementSupport] = useState<number>(3);
  const [compensationSatisfaction, setCompensationSatisfaction] = useState<number>(3);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);

  return (
    <section className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="space-y-2 rounded-xl border border-indigo-200 bg-indigo-50/60 p-4 text-xs text-slate-800 dark:border-indigo-900 dark:bg-indigo-950/40 dark:text-slate-200">
        <h2 className="text-sm font-bold text-indigo-950 dark:text-indigo-200">
          {translate("workplace.consentHeading")}
        </h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>{translate("workplace.consentBullet1")}</li>
          <li>{translate("workplace.consentBullet2")}</li>
          <li>{translate("workplace.consentBullet3")}</li>
          <li>{translate("workplace.consentBullet4")}</li>
        </ul>
      </div>

      {statusNotice ? (
        <div
          role="status"
          className="rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-xs font-semibold text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200"
        >
          {statusNotice}
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="contrib-industry" label="Industry Category (Broad)">
          <select
            id="contrib-industry"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="technology">Technology & Software</option>
            <option value="finance">Finance & Banking</option>
            <option value="healthcare">Healthcare</option>
            <option value="education">Education</option>
            <option value="consulting_services">Consulting & Services</option>
            <option value="other">Other</option>
          </select>
        </FormField>

        <FormField id="contrib-role" label="Role / Job Family">
          <select
            id="contrib-role"
            value={roleFamily}
            onChange={(e) => setRoleFamily(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="software_engineering">Software Engineering</option>
            <option value="product_design">Product & Design</option>
            <option value="data_analytics">Data & Analytics</option>
            <option value="operations_support">Operations & Support</option>
            <option value="management_leadership">Management & Leadership</option>
            <option value="other">Other</option>
          </select>
        </FormField>

        <FormField id="contrib-exp" label="Experience Band">
          <select
            id="contrib-exp"
            value={experienceBand}
            onChange={(e) => setExperienceBand(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="fresher_0_1">0–1 years (Fresher)</option>
            <option value="junior_1_3">1–3 years (Junior)</option>
            <option value="mid_3_6">3–6 years (Mid-Level)</option>
            <option value="senior_6_10">6–10 years (Senior)</option>
            <option value="lead_10_plus">10+ years (Lead)</option>
          </select>
        </FormField>

        <FormField id="contrib-arr" label="Workplace Arrangement">
          <select
            id="contrib-arr"
            value={workArrangement}
            onChange={(e) => setWorkArrangement(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">On-Site</option>
          </select>
        </FormField>
      </div>

      <div className="grid gap-4 border-t border-slate-100 pt-4 sm:grid-cols-2 dark:border-slate-800">
        <FormField
          id="rating-overall"
          label="Overall Workplace Satisfaction (1 = Very poor, 5 = Very good)"
        >
          <input
            id="rating-overall"
            type="number"
            min={1}
            max={5}
            value={overallSatisfaction}
            onChange={(e) => setOverallSatisfaction(Number(e.target.value))}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
        </FormField>

        <FormField
          id="rating-wlb"
          label="Work-Life Balance (1 = Very poor, 5 = Very good)"
        >
          <input
            id="rating-wlb"
            type="number"
            min={1}
            max={5}
            value={workLifeBalance}
            onChange={(e) => setWorkLifeBalance(Number(e.target.value))}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
        </FormField>

        <FormField
          id="rating-mgmt"
          label="Management Support (1 = Very poor, 5 = Very good)"
        >
          <input
            id="rating-mgmt"
            type="number"
            min={1}
            max={5}
            value={managementSupport}
            onChange={(e) => setManagementSupport(Number(e.target.value))}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
        </FormField>

        <FormField
          id="rating-comp"
          label="Compensation Satisfaction (Sensitive: requires n >= 20 to display)"
        >
          <input
            id="rating-comp"
            type="number"
            min={1}
            max={5}
            value={compensationSatisfaction}
            onChange={(e) => setCompensationSatisfaction(Number(e.target.value))}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
        </FormField>
      </div>

      <label className="flex items-start gap-2.5 text-xs font-medium text-slate-800 dark:text-slate-200">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          className="mt-0.5"
        />
        <span>{translate("workplace.consentCheckboxLabel")}</span>
      </label>

      <div className="flex flex-wrap gap-3 pt-2">
        <Button
          disabled={!consent}
          onClick={() =>
            setStatusNotice(
              "Structured contribution saved! Your response is included only in k-anonymity protected aggregates."
            )
          }
        >
          {translate("workplace.submitContributionButton")}
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            setConsent(false);
            setStatusNotice(
              "Aggregation consent withdrawn. Your record is immediately excluded from all aggregate calculations."
            );
          }}
        >
          {translate("workplace.withdrawConsentButton")}
        </Button>
        <Button
          variant="secondary"
          onClick={() =>
            setStatusNotice(
              "Your structured contribution has been permanently deleted and removed from future aggregates."
            )
          }
        >
          {translate("workplace.deleteContributionButton")}
        </Button>
      </div>
    </section>
  );
}
