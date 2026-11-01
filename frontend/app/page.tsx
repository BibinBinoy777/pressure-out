"use client";

import React, { useState } from "react";
import { Container } from "../components/Container";
import { BackendHealthStatus } from "../components/BackendHealthStatus";
import { FeedModeTabs } from "../components/feed/FeedModeTabs";
import type { FeedMode } from "../lib/api-client";
import { getCatalog, translate } from "../lib/i18n";

export default function HomePage() {
  const [feedMode, setFeedMode] = useState<FeedMode>("popular");
  const [languageFilter, setLanguageFilter] = useState<string>("");
  const [postTypeFilter, setPostTypeFilter] = useState<string>("");

  const catalog = getCatalog("en");
  const pillars = [
    catalog.pillars.items.community,
    catalog.pillars.items.identity,
    catalog.pillars.items.memeStudio,
    catalog.pillars.items.multilingual,
  ];

  return (
    <Container className="space-y-10">
      <section aria-labelledby="hero-heading" className="space-y-4">
        <div className="inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-800 dark:border-indigo-900 dark:bg-indigo-950/60 dark:text-indigo-300">
          <span>{translate("hero.eyebrow")}</span>
          <span aria-hidden="true">•</span>
          <span>{translate("brand.tagline")}</span>
        </div>

        <h1
          id="hero-heading"
          className="text-3xl font-extrabold tracking-tight text-slate-900 sm:text-5xl dark:text-white"
        >
          {translate("hero.headline")}
        </h1>

        <p className="text-lg font-medium text-indigo-700 dark:text-indigo-300">
          {translate("brand.secondaryTagline")}
        </p>

        <p className="max-w-3xl text-base leading-relaxed text-slate-700 dark:text-slate-300">
          {translate("hero.description")}
        </p>
      </section>

      <FeedModeTabs
        activeMode={feedMode}
        selectedLanguage={languageFilter}
        selectedPostType={postTypeFilter}
        onModeChange={setFeedMode}
        onLanguageChange={setLanguageFilter}
        onPostTypeChange={setPostTypeFilter}
      />

      <section id="pillars-section" aria-labelledby="pillars-heading" className="space-y-6">
        <h2
          id="pillars-heading"
          className="text-xl font-bold tracking-tight text-slate-900 dark:text-white"
        >
          {translate("pillars.sectionTitle")}
        </h2>

        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          {pillars.map((pillar) => (
            <article
              key={pillar.title}
              className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900"
            >
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">
                {pillar.title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                {pillar.description}
              </p>
            </article>
          ))}
        </div>
      </section>

      <BackendHealthStatus />
    </Container>
  );
}
