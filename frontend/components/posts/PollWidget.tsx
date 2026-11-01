"use client";

import React, { useState } from "react";
import type { PublicPollResponse } from "../../lib/api-client";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface PollWidgetProps {
  poll: PublicPollResponse;
  onVote?: (selectedIds: string[]) => void;
}

export function PollWidget({ poll, onVote }: PollWidgetProps) {
  const [selected, setSelected] = useState<string[]>(
    poll.viewer_selected_option_ids || []
  );
  const hasVoted = (poll.viewer_selected_option_ids || []).length > 0;

  const toggleOption = (id: string) => {
    if (hasVoted) return;
    if (poll.allows_multiple) {
      setSelected((prev) =>
        prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
      );
    } else {
      setSelected([id]);
    }
  };

  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-900/60">
      <div className="space-y-2">
        {poll.options.map((opt) => {
          const isChecked = selected.includes(opt.id);
          return (
            <div
              key={opt.id}
              onClick={() => toggleOption(opt.id)}
              className={`cursor-pointer rounded-lg border p-3 transition-colors ${
                isChecked
                  ? "border-indigo-600 bg-indigo-50/60 dark:border-indigo-400 dark:bg-indigo-950/40"
                  : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
              }`}
            >
              <div className="flex items-center justify-between text-sm font-medium text-slate-900 dark:text-slate-100">
                <span>{opt.option_text}</span>
                <span className="text-xs text-slate-600 dark:text-slate-400">
                  {opt.percentage}% ({opt.vote_count})
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between pt-1 text-xs text-slate-600 dark:text-slate-400">
        <span>
          {translate("posts.pollTotalVotes", { count: poll.total_votes })}
        </span>
        {!hasVoted && onVote ? (
          <Button
            variant="primary"
            disabled={selected.length === 0}
            onClick={() => onVote(selected)}
          >
            {translate("posts.pollVoteButton")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
