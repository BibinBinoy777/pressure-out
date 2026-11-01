import React from "react";
import { FormField } from "../FormField";
import { translate } from "../../lib/i18n";

export interface AlternativeTextEditorProps {
  altText: string;
  onChange: (altText: string) => void;
}

export function AlternativeTextEditor({
  altText,
  onChange,
}: AlternativeTextEditorProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <FormField
        id="meme-alt-text-input"
        label={`${translate("memeStudio.altTextLabel")} (${altText.length}/500)`}
        hint={translate("memeStudio.altTextHint")}
      >
        <input
          id="meme-alt-text-input"
          type="text"
          maxLength={500}
          value={altText}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Auto-generated from template and captions if left blank..."
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
      </FormField>
    </div>
  );
}
