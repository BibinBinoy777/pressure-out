import React from "react";
import { Container } from "./Container";
import { translate } from "../lib/i18n";
import { UiLocaleSwitcher } from "./i18n/UiLocaleSwitcher";

export function Navbar() {
  return (
    <header className="border-b border-slate-200 bg-white/95 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95">
      <Container className="flex h-16 items-center justify-between">
        <div className="flex items-center gap-3">
          <a
            href="/"
            className="rounded-md text-lg font-bold tracking-tight text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-white"
          >
            {translate("brand.name")}
          </a>
          <span className="hidden rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700 sm:inline-block dark:bg-indigo-950 dark:text-indigo-300">
            {translate("brand.phaseBadge")}
          </span>
        </div>

        <nav aria-label={translate("a11y.mainNavigation")} className="flex items-center gap-3 sm:gap-4">
          <a
            href="/explore"
            className="rounded-md px-2 py-1 text-sm font-medium text-slate-700 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-slate-300 dark:hover:text-white"
          >
            {translate("nav.explore")}
          </a>
          <a
            href="/workplace/experiences"
            className="rounded-md px-2 py-1 text-sm font-medium text-slate-700 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-slate-300 dark:hover:text-white"
          >
            {translate("nav.workplaceExperiences")}
          </a>
          <a
            href="/workplace/resignations"
            className="rounded-md px-2 py-1 text-sm font-medium text-slate-700 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-slate-300 dark:hover:text-white"
          >
            {translate("nav.resignations")}
          </a>
          <a
            href="/insights/workplace"
            className="rounded-md px-2 py-1 text-sm font-medium text-slate-700 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-slate-300 dark:hover:text-white"
          >
            {translate("nav.insights")}
          </a>
          <a
            href="/communities" 
            className="rounded-md px-2 py-1 text-sm font-medium text-slate-700 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-slate-300 dark:hover:text-white"
          >
            {translate("nav.communities")}
          </a>
          <a
            href="/search"
            className="rounded-md px-2 py-1 text-sm font-medium text-slate-700 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-slate-300 dark:hover:text-white"
          >
            {translate("nav.search")}
          </a>
          <a
            href="/meme-studio"
            className="rounded-md px-2 py-1 text-sm font-semibold text-indigo-600 hover:text-indigo-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-200"
          >
            {translate("nav.memeStudio")}
          </a>
          <a
            href="/create" 
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            {translate("nav.createPost")}
          </a>
          <UiLocaleSwitcher />
        </nav>
      </Container>
    </header>
  );
}
