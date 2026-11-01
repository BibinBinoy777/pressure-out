"use client";

import React from "react";
import type { ReactionKind } from "../../lib/api-client";
import { translate } from "../../lib/i18n";

export interface ReactionBarProps {
  reactionCounts: Record<string, number>;
  viewerReactions?: string[];
  onToggleReaction?: (kind: ReactionKind, nextActive: boolean) => void;
}

const REACTION_KINDS: ReactionKind[] = [
  "relatable",
  "laugh",
  "support",
  "oof",
  "respect",
];

export function ReactionBar({
  reactionCounts,
  viewerReactions = [],
  onToggleReaction,
}: ReactionBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {REACTION_KINDS.map((kind) => {
        const count = reactionCounts[kind] ?? 0;
        const isActive = viewerReactions.includes(kind);

        return (
          <button
            key={kind}
            type="button"
            aria-pressed={isActive}
            onClick={() =>
              onToggleReaction ? onToggleReaction(kind, !isActive) : undefined
            }
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
              isActive
                ? "border-indigo-500 bg-indigo-50 text-indigo-800 dark:border-indigo-400 dark:bg-indigo-950/60 dark:text-indigo-200"
                : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
            }`}
          >
            <span>{translate(`engagement.reactions.${kind}`)}</span>
            {count > 0 ? (
              <span className="font-semibold">{count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
