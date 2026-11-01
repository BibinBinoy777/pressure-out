import React from "react";
import type { MemeTemplateResponse } from "../../lib/api-client";
import { TemplateCard } from "./TemplateCard";
import { translate } from "../../lib/i18n";

export interface TemplateGalleryProps {
  templates: MemeTemplateResponse[];
  selectedTemplateSlug: string;
  selectedCategory: string;
  onCategoryChange: (category: string) => void;
  onSelectTemplate: (template: MemeTemplateResponse) => void;
}

const CATEGORIES = [
  "all",
  "engineering",
  "meetings",
  "product",
  "compensation",
  "job-hunting",
  "communication",
];

export function TemplateGallery({
  templates,
  selectedTemplateSlug,
  selectedCategory,
  onCategoryChange,
  onSelectTemplate,
}: TemplateGalleryProps) {
  const filtered =
    selectedCategory === "all"
      ? templates
      : templates.filter((t) => t.category === selectedCategory);

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-900 dark:text-white">
          {translate("memeStudio.templateGalleryHeading")}
        </h2>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter templates by category">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => onCategoryChange(cat)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium capitalize ${
                selectedCategory === cat
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
          No workplace templates found in this category.
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((tmpl) => (
            <TemplateCard
              key={tmpl.id}
              template={tmpl}
              isSelected={tmpl.slug === selectedTemplateSlug}
              onSelect={onSelectTemplate}
            />
          ))}
        </div>
      )}
    </section>
  );
}
