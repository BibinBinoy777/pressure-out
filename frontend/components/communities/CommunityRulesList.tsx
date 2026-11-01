import React from "react";
import type { CommunityRuleResponse } from "../../lib/api-client";
import { translate } from "../../lib/i18n";

export interface CommunityRulesListProps {
  rules: CommunityRuleResponse[];
}

export function CommunityRulesList({ rules }: CommunityRulesListProps) {
  return (
    <aside
      aria-label={translate("communities.rulesHeading")}
      className="space-y-3 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      <h2 className="text-sm font-bold uppercase tracking-wider text-slate-900 dark:text-white">
        {translate("communities.rulesHeading")}
      </h2>

      <ol className="space-y-3 text-sm">
        {rules.map((rule) => (
          <li
            key={rule.rule_number}
            className="border-b border-slate-100 pb-2.5 last:border-b-0 last:pb-0 dark:border-slate-800"
          >
            <p className="font-semibold text-slate-900 dark:text-slate-100">
              {rule.rule_number}. {rule.title}
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-slate-600 dark:text-slate-400">
              {rule.description}
            </p>
          </li>
        ))}
      </ol>
    </aside>
  );
}
