"use client";

import React from "react";
import { translate } from "../../lib/i18n";

export interface AnonymousOpLockBannerProps {
  unlocked: boolean;
  onToggleUnlock: (unlocked: boolean) => void;
}

/**
 * Sticky Anonymous OP protection banner (`AC-IMP-06`).
 * Displayed whenever the author of an anonymous post replies in their own thread.
 */
export function AnonymousOpLockBanner({
  unlocked,
  onToggleUnlock,
}: AnonymousOpLockBannerProps) {
  return (
    <div
      role="region"
      aria-label={translate("comments.opLockTitle")}
      className="space-y-2 rounded-xl border border-indigo-300 bg-indigo-50/80 p-4 text-xs text-indigo-950 dark:border-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-200"
    >
      <p className="font-bold">{translate("comments.opLockTitle")}</p>
      <p>{translate("comments.opLockDescription")}</p>
      <label className="flex cursor-pointer items-center gap-2 pt-1 font-medium">
        <input
          type="checkbox"
          checked={unlocked}
          onChange={(e) => onToggleUnlock(e.target.checked)}
          className="h-4 w-4 rounded border-indigo-400 text-indigo-600"
        />
        <span>{translate("comments.opUnlockCheckbox")}</span>
      </label>
    </div>
  );
}
