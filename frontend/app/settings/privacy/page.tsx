"use client";

import React, { useState } from "react";
import { Container } from "../../../components/Container";
import { Button } from "../../../components/Button";
import { IdentityModeSelector } from "../../../components/identity/IdentityModeSelector";
import type { BlockedAccountItem, IdentityMode } from "../../../lib/api-client";
import { translate } from "../../../lib/i18n";

const SAMPLE_BLOCKED: BlockedAccountItem[] = [
  {
    handle: "noisy_recruiter",
    display_name: "@noisy_recruiter",
    mode: "mute",
    created_at: "2026-10-29T00:00:00Z",
  },
];

export default function PrivacySettingsPage() {
  const [defaultMode, setDefaultMode] = useState<IdentityMode>("pseudonymous");
  const [blockedList, setBlockedList] = useState<BlockedAccountItem[]>(SAMPLE_BLOCKED);

  return (
    <Container className="max-w-2xl space-y-8">
      <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
        {translate("settings.privacyTitle")}
      </h1>

      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">
          {translate("settings.defaultIdentityHeading")}
        </h2>
        <IdentityModeSelector value={defaultMode} onChange={setDefaultMode} />
      </section>

      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">
            {translate("moderation.blockedMutedHeading")}
          </h2>
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
            {translate("moderation.blockedMutedDescription")}
          </p>
        </div>

        {blockedList.length === 0 ? (
          <p className="text-xs text-slate-500">
            You have no blocked or muted accounts.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {blockedList.map((item) => (
              <li
                key={item.handle}
                className="flex items-center justify-between py-2.5 text-sm"
              >
                <div>
                  <span className="font-semibold text-slate-900 dark:text-white">
                    @{item.handle}
                  </span>{" "}
                  <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs uppercase text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {item.mode}
                  </span>
                </div>
                <Button
                  variant="outline"
                  onClick={() =>
                    setBlockedList((prev) =>
                      prev.filter((x) => x.handle !== item.handle)
                    )
                  }
                >
                  {item.mode === "block"
                    ? translate("moderation.unblockButton")
                    : translate("moderation.unmuteButton")}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">
          {translate("settings.sessionsHeading")}
        </h2>
        <Button variant="outline">
          {translate("settings.revokeAllSessionsButton")}
        </Button>
      </section>

      <section className="space-y-4 rounded-xl border border-red-300 bg-red-50/60 p-6 dark:border-red-900/60 dark:bg-red-950/30">
        <h2 className="text-base font-semibold text-red-900 dark:text-red-200">
          {translate("settings.deleteAccountHeading")}
        </h2>
        <p className="text-sm text-red-800 dark:text-red-300">
          {translate("settings.deleteAccountWarning")}
        </p>
        <Button variant="secondary">
          {translate("settings.deleteAccountButton")}
        </Button>
      </section>
    </Container>
  );
}
