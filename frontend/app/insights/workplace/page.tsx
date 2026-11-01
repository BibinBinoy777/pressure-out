"use client";

import React, { useState } from "react";
import { Container } from "../../../components/Container";
import { WorkplaceInsightCard } from "../../../components/workplace/WorkplaceInsightCard";
import type { AggregatedRatingMetricCard } from "../../../lib/api-client";
import { translate } from "../../../lib/i18n";

const SAMPLE_METRICS: AggregatedRatingMetricCard[] = [
  {
    metric_key: "overall_satisfaction",
    label: "Overall Workplace Satisfaction",
    is_sensitive: false,
    minimum_threshold: 10,
    insufficient_data: false,
    sample_size_band: "15+",
    average_rating: 3.8,
    median_rating: 4.0,
    rating_distribution_pct: { "1": 5, "2": 10, "3": 20, "4": 45, "5": 20 },
    status_message: "Privacy threshold satisfied.",
  },
  {
    metric_key: "work_life_balance",
    label: "Work-Life Balance",
    is_sensitive: false,
    minimum_threshold: 10,
    insufficient_data: false,
    sample_size_band: "15+",
    average_rating: 3.6,
    median_rating: 4.0,
    rating_distribution_pct: { "1": 10, "2": 10, "3": 25, "4": 40, "5": 15 },
    status_message: "Privacy threshold satisfied.",
  },
  {
    metric_key: "compensation_satisfaction",
    label: "Compensation Satisfaction (Sensitive)",
    is_sensitive: true,
    minimum_threshold: 20,
    insufficient_data: true,
    sample_size_band: null,
    average_rating: null,
    median_rating: null,
    rating_distribution_pct: null,
    status_message:
      "Not enough contributions yet to display a privacy-protected result for this group.",
  },
];

export default function WorkplaceInsightsPage() {
  const [industryFilter, setIndustryFilter] = useState<string>("all");
  const [arrangementFilter, setArrangementFilter] = useState<string>("all");

  return (
    <Container className="space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-6 dark:border-slate-800">
        <div className="space-y-2">
          <span className="inline-block rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300">
            k-Anonymity Protected • No Employer Leaderboard
          </span>
          <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white">
            {translate("workplace.insightsPageTitle")}
          </h1>
          <p className="max-w-3xl text-sm text-slate-600 dark:text-slate-400">
            {translate("workplace.insightsPageSubtitle")}
          </p>
        </div>

        <a
          href="/workplace/share-experience"
          className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700"
        >
          {translate("nav.shareContribution")} →
        </a>
      </header>

      <section className="flex flex-wrap items-center gap-4 rounded-xl border border-slate-200 bg-white p-4 text-xs dark:border-slate-800 dark:bg-slate-900">
        <span className="font-bold text-slate-700 dark:text-slate-300">
          Broad Cohort Filters (Max 2 simultaneous dimensions):
        </span>
        <label className="flex items-center gap-1.5 font-medium">
          Industry:
          <select
            value={industryFilter}
            onChange={(e) => setIndustryFilter(e.target.value)}
            className="rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="all">All Industries</option>
            <option value="technology">Technology & Software</option>
            <option value="finance">Finance & Banking</option>
            <option value="healthcare">Healthcare</option>
          </select>
        </label>

        <label className="flex items-center gap-1.5 font-medium">
          Work Arrangement:
          <select
            value={arrangementFilter}
            onChange={(e) => setArrangementFilter(e.target.value)}
            className="rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="all">All Arrangements</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">On-Site</option>
          </select>
        </label>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SAMPLE_METRICS.map((m) => (
          <WorkplaceInsightCard key={m.metric_key} metric={m} />
        ))}
      </div>

      <section className="space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-5 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-400">
        <h2 className="font-bold text-slate-900 dark:text-white">
          {translate("workplace.methodologyTitle")}
        </h2>
        <p>
          Derived exclusively from voluntary, explicitly consented structured contributions (`workplace_insight_contributions`). Free-text posts, resignation stories, comments, and reports are never fed into the aggregation engine.
        </p>
        <p>
          General workplace indicators require at least <strong>10 distinct contributors</strong> (`n &ge; 10`), and sensitive compensation and resignation-reason breakdowns require at least <strong>20 distinct contributors</strong> (`n &ge; 20`) with complementary small-bucket suppression (`n &lt; 3`). All responses are self-reported, unverified, and not statistically representative of an entire industry or workforce.
        </p>
      </section>
    </Container>
  );
}
