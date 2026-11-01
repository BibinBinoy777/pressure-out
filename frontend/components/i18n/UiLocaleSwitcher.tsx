"use client";

import React from "react";
import {
  SUPPORTED_UI_LOCALES,
  SupportedUiLocale,
  getActiveUiLocale,
  setActiveUiLocale,
  translate,
} from "../../lib/i18n";

export interface UiLocaleSwitcherProps {
  value?: SupportedUiLocale;
  onChange?: (nextLocale: SupportedUiLocale) => void;
}

export function UiLocaleSwitcher({
  value,
  onChange,
}: UiLocaleSwitcherProps) {
  const active = value ?? getActiveUiLocale();

  const handleSelect = (nextCode: string) => {
    const resolved = setActiveUiLocale(nextCode);
    if (onChange) {
      onChange(resolved);
    }
  };

  return (
    <div className="inline-flex items-center gap-1.5">
      <label
        htmlFor="ui-locale-switcher"
        className="sr-only"
      >
        {translate("localeSwitcher.ariaLabel", undefined, active)}
      </label>
      <select
        id="ui-locale-switcher"
        aria-label={translate("localeSwitcher.ariaLabel", undefined, active)}
        title={translate("localeSwitcher.separateFromContentHint", undefined, active)}
        value={active}
        onChange={(e) => handleSelect(e.target.value)}
        className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-800 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
      >
        {SUPPORTED_UI_LOCALES.map((loc) => (
          <option key={loc.code} value={loc.code}>
            {loc.nativeName} ({loc.code.toUpperCase()})
          </option>
        ))}
      </select>
    </div>
  );
}
