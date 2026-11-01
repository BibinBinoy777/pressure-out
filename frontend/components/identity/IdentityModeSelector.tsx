"use client";

import React from "react";
import type { IdentityMode } from "../../lib/api-client";
import { translate } from "../../lib/i18n";

export interface IdentityModeSelectorProps {
  value: IdentityMode;
  onChange: (mode: IdentityMode) => void;
  hasProfessionalProfile?: boolean;
  disabled?: boolean;
}

const MODES: IdentityMode[] = ["pseudonymous", "anonymous", "professional"];

export function IdentityModeSelector({
  value,
  onChange,
  hasProfessionalProfile = true,
  disabled = false,
}: IdentityModeSelectorProps) {
  return (
    <fieldset className="space-y-3" disabled={disabled}>
      <legend className="text-sm font-semibold text-slate-900 dark:text-slate-100">
        {translate("identity.selectorLabel")}
      </legend>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {MODES.map((mode) => {
          const isSelected = value === mode;
          const isProfDisabled = mode === "professional" && !hasProfessionalProfile;

          return (
            <label
              key={mode}
              className={`flex cursor-pointer flex-col justify-between rounded-xl border p-3.5 text-left transition-colors ${
                isSelected
                  ? "border-indigo-600 bg-indigo-50/70 dark:border-indigo-400 dark:bg-indigo-950/40"
                  : "border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900"
              } ${isProfDisabled ? "cursor-not-allowed opacity-60" : ""}`}
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="identity_mode"
                    value={mode}
                    checked={isSelected}
                    disabled={disabled || isProfDisabled}
                    onChange={() => onChange(mode)}
                    className="h-4 w-4 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-sm font-semibold text-slate-900 dark:text-white">
                    {translate(`identity.modes.${mode}.label`)}
                  </span>
                </div>
                <p className="pl-6 text-xs text-slate-600 dark:text-slate-400">
                  {translate(`identity.modes.${mode}.description`)}
                </p>
              </div>
            </label>
          );
        })}
      </div>

      {value === "anonymous" ? (
        <div
          role="note"
          className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-800/70 dark:bg-amber-950/40 dark:text-amber-200"
        >
          {translate("identity.modes.anonymous.honestyReminder")}
        </div>
      ) : null}
    </fieldset>
  );
}
