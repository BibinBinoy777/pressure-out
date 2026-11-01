import React from "react";
import { Container } from "../../../components/Container";
import { StructuredContributionForm } from "../../../components/workplace/StructuredContributionForm";
import { translate } from "../../../lib/i18n";

export default function ShareStructuredExperiencePage() {
  return (
    <Container className="max-w-3xl space-y-6">
      <header className="space-y-2 border-b border-slate-200 pb-5 dark:border-slate-800">
        <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white">
          {translate("workplace.shareContributionTitle")}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {translate("workplace.shareContributionSubtitle")}
        </p>
      </header>

      <StructuredContributionForm />
    </Container>
  );
}
