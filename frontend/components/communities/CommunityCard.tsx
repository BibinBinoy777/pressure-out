import React from "react";
import type { CommunitySummaryResponse } from "../../lib/api-client";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface CommunityCardProps {
  community: CommunitySummaryResponse;
  onToggleMembership?: (slug: string, nextAction: "join" | "leave") => void;
}

export function CommunityCard({ community, onToggleMembership }: CommunityCardProps) {
  const isMember = community.viewer_context.is_member;

  return (
    <article className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="space-y-2.5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <a
              href={`/c/${encodeURIComponent(community.slug)}`}
              className="text-base font-bold text-slate-900 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-white"
            >
              {community.name}
            </a>
            <p className="text-xs font-medium text-indigo-700 dark:text-indigo-300">
              c/{community.slug}
            </p>
          </div>

          <span className="rounded-md border border-slate-200 px-1.5 py-0.5 font-mono text-xs uppercase text-slate-600 dark:border-slate-700 dark:text-slate-300">
            {community.primary_language}
          </span>
        </div>

        <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400">
          {community.description}
        </p>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 dark:border-slate-800">
        <div className="flex items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
          <span>
            {translate("communities.memberCountLabel", {
              count: community.member_count,
            })}
          </span>
          <span aria-hidden="true">•</span>
          <span>
            {translate("communities.postCountLabel", {
              count: community.post_count,
            })}
          </span>
        </div>

        {onToggleMembership ? (
          <Button
            variant={isMember ? "outline" : "primary"}
            disabled={community.viewer_context.is_banned}
            onClick={() =>
              onToggleMembership(community.slug, isMember ? "leave" : "join")
            }
          >
            {isMember
              ? translate("communities.joinedButton")
              : translate("communities.joinButton")}
          </Button>
        ) : null}
      </div>
    </article>
  );
}
