"use client";

import React from "react";
import type { FeedMode, PostType } from "../../lib/api-client";
import { translate } from "../../lib/i18n";

export interface FeedModeTabsProps {
  activeMode: FeedMode;
  selectedLanguage: string;
  selectedPostType: string;
  onModeChange: (mode: FeedMode) => void;
  onLanguageChange: (lang: string) => void;
  onPostTypeChange: (postType: string) => void;
}

const MODES: FeedMode[] = ["popular", "latest", "following"];
const FILTER_LANGUAGES = ["", "en", "ml", "hi", "ta", "es", "mul"];
const FILTER_POST_TYPES: Array<"" | PostType> = [
  "",
  "discussion",
  "rant",
  "meme",
  "question",
  "poll",
  "story",
  "advice_request",
  "workplace_experience",
];

export function FeedModeTabs({
  activeMode,
  selectedLanguage,
  selectedPostType,
  onModeChange,
  onLanguageChange,
  onPostTypeChange,
}: FeedModeTabsProps) {
  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div role="tablist" aria-label="Feed Modes" className="inline-flex rounded-lg bg-slate-100 p-1 dark:bg-slate-800">
          {MODES.map((m) => {
            const isSelected = activeMode === m;
            return (
              <button
                key={m}
                role="tab"
                type="button"
                aria-selected={isSelected}
                onClick={() => onModeChange(m)}
                className={`rounded-md px-4 py-1.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                  isSelected
                    ? "bg-white text-indigo-700 shadow-sm dark:bg-slate-950 dark:text-indigo-300"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-400"
                }`}
              >
                {translate(`feed.modes.${m}`)}
              </button>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="feed-lang-filter" className="sr-only">
            {translate("feed.filterLanguageLabel")}
          </label>
          <select
            id="feed-lang-filter"
            value={selectedLanguage}
            onChange={(e) => onLanguageChange(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium dark:border-slate-700 dark:bg-slate-950"
          >
            {FILTER_LANGUAGES.map((lang) => (
              <option key={lang || "all"} value={lang}>
                {lang ? translate(`posts.languages.${lang}`) : translate("feed.allLanguages")}
              </option>
            ))}
          </select>

          <label htmlFor="feed-type-filter" className="sr-only">
            {translate("feed.filterTypeLabel")}
          </label>
          <select
            id="feed-type-filter"
            value={selectedPostType}
            onChange={(e) => onPostTypeChange(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium dark:border-slate-700 dark:bg-slate-950"
          >
            {FILTER_POST_TYPES.map((pt) => (
              <option key={pt || "all"} value={pt}>
                {pt ? translate(`posts.types.${pt}`) : translate("feed.allTypes")}
              </option>
            ))}
          </select>
        </div>
      </div>

      {activeMode === "popular" ? (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {translate("feed.rankingDisclaimer")}
        </p>
      ) : null}
    </div>
  );
}
