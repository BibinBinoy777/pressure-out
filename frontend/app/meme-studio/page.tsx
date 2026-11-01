import React from "react";
import { Container } from "../../components/Container";
import { MemeStudio } from "../../components/meme-studio/MemeStudio";
import { translate } from "../../lib/i18n";

export default function MemeStudioPage() {
  return (
    <Container className="space-y-8">
      <header className="space-y-2 border-b border-slate-200 pb-6 dark:border-slate-800">
        <span className="inline-block rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300">
          {translate("brand.phaseBadge")}
        </span>
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
          {translate("memeStudio.pageTitle")}
        </h1>
        <p className="max-w-3xl text-sm text-slate-600 dark:text-slate-400">
          {translate("memeStudio.pageSubtitle")}
        </p>
      </header>

      <MemeStudio />
    </Container>
  );
}
