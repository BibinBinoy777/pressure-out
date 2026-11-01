import React from "react";
import type { MemeTemplateResponse } from "../../lib/api-client";

export interface TemplateCardProps {
  template: MemeTemplateResponse;
  isSelected: boolean;
  onSelect: (template: MemeTemplateResponse) => void;
}

export function TemplateCard({
  template,
  isSelected,
  onSelect,
}: TemplateCardProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect(template)}
      aria-pressed={isSelected}
      className={`flex flex-col justify-between rounded-xl border p-4 text-left transition ${
        isSelected
          ? "border-indigo-600 bg-indigo-50/70 ring-2 ring-indigo-500 dark:border-indigo-400 dark:bg-indigo-950/50"
          : "border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900"
      }`}
    >
      <div>
        <div className="flex items-center justify-between gap-2">
          <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            {template.category}
          </span>
          <span className="text-xs font-mono text-slate-500">
            {template.aspect_ratio} • {template.text_regions.length} regions
          </span>
        </div>
        <h3 className="mt-2 text-base font-bold text-slate-900 dark:text-white">
          {template.name}
        </h3>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
          {template.description}
        </p>
      </div>
      <div className="mt-3 flex flex-wrap gap-1 border-t border-slate-100 pt-2 text-[11px] text-slate-500 dark:border-slate-800">
        {template.category_tags.map((tag) => (
          <span key={tag}>#{tag}</span>
        ))}
      </div>
    </button>
  );
}
