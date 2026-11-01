"use client";

import React from "react";
import { translate } from "../../lib/i18n";

export interface VoteControlsProps {
  score: number;
  viewerVote?: number;
  onVote?: (nextValue: 1 | -1 | 0) => void;
}

export function VoteControls({
  score,
  viewerVote = 0,
  onVote,
}: VoteControlsProps) {
  const handleUp = () => {
    if (!onVote) return;
    onVote(viewerVote === 1 ? 0 : 1);
  };

  const handleDown = () => {
    if (!onVote) return;
    onVote(viewerVote === -1 ? 0 : -1);
  };

  return (
    <div className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-xs font-semibold dark:border-slate-800 dark:bg-slate-900">
      <button
        type="button"
        aria-label={translate("engagement.upvoteAria")}
        aria-pressed={viewerVote === 1}
        onClick={handleUp}
        className={`rounded-full px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
          viewerVote === 1
            ? "text-indigo-600 dark:text-indigo-400"
            : "text-slate-600 hover:text-slate-900 dark:text-slate-400"
        }`}
      >
        ▲
      </button>
      <span className="px-1.5 text-slate-900 dark:text-slate-100">{score}</span>
      <button
        type="button"
        aria-label={translate("engagement.downvoteAria")}
        aria-pressed={viewerVote === -1}
        onClick={handleDown}
        className={`rounded-full px-2 py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
          viewerVote === -1
            ? "text-amber-600 dark:text-amber-400"
            : "text-slate-600 hover:text-slate-900 dark:text-slate-400"
        }`}
      >
        ▼
      </button>
    </div>
  );
}
