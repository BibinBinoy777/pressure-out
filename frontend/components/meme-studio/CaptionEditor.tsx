import React from "react";
import type { MemeTextRegion } from "../../lib/api-client";
import { FormField } from "../FormField";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface CaptionEditorProps {
  regions: MemeTextRegion[];
  captionValues: Record<string, string>;
  language: string;
  outputFormat: "PNG" | "WEBP";
  isRendering?: boolean;
  onCaptionChange: (regionId: string, text: string) => void;
  onLanguageChange: (lang: string) => void;
  onOutputFormatChange: (fmt: "PNG" | "WEBP") => void;
  onRenderMeme: () => void;
}

const LANGUAGES = [
  { code: "en", label: "English (en)" },
  { code: "ml", label: "Malayalam — മലയാളം (ml)" },
  { code: "hi", label: "Hindi — हिन्दी (hi)" },
  { code: "ta", label: "Tamil — தமிழ் (ta)" },
  { code: "mul", label: "Mixed / Manglish / Hinglish (mul)" },
];

export function CaptionEditor({
  regions,
  captionValues,
  language,
  outputFormat,
  isRendering = false,
  onCaptionChange,
  onLanguageChange,
  onOutputFormatChange,
  onRenderMeme,
}: CaptionEditorProps) {
  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-900 dark:text-white">
          {translate("memeStudio.captionEditorHeading")}
        </h2>
        <div className="flex items-center gap-2">
          <label htmlFor="meme-lang-select" className="text-xs font-medium text-slate-600 dark:text-slate-400">
            Script / Language:
          </label>
          <select
            id="meme-lang-select"
            value={language}
            onChange={(e) => onLanguageChange(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>

          <select
            aria-label="Output image format"
            value={outputFormat}
            onChange={(e) => onOutputFormatChange(e.target.value as "PNG" | "WEBP")}
            className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs font-mono text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
          >
            <option value="PNG">PNG</option>
            <option value="WEBP">WEBP</option>
          </select>
        </div>
      </div>

      <div className="space-y-3">
        {regions.map((region) => {
          const val = captionValues[region.id] || "";
          return (
            <FormField
              key={region.id}
              id={`caption-region-${region.id}`}
              label={`${region.label} (${val.length}/${region.max_chars})`}
              hint="Supports full Unicode, Indic scripts, and emojis."
            >
              <input
                id={`caption-region-${region.id}`}
                type="text"
                maxLength={region.max_chars}
                value={val}
                onChange={(e) => onCaptionChange(region.id, e.target.value)}
                placeholder={`Enter ${region.label.toLowerCase()}...`}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-white"
              />
            </FormField>
          );
        })}
      </div>

      <div className="pt-2">
        <Button onClick={onRenderMeme} disabled={isRendering}>
          {isRendering ? "Rendering Meme..." : translate("memeStudio.renderTemplateButton")}
        </Button>
      </div>
    </section>
  );
}
