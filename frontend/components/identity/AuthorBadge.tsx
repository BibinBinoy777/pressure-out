import React from "react";
import type { PublicAuthorDisplay } from "../../lib/api-client";
import { translate } from "../../lib/i18n";

export interface AuthorBadgeProps {
  author: PublicAuthorDisplay;
}

/**
 * Renders a post or comment author strictly from the backend's serialized
 * `PublicAuthorDisplay` contract, ensuring anonymous authors never render
 * profile links or handles.
 */
export function AuthorBadge({ author }: AuthorBadgeProps) {
  if (author.identity_mode === "anonymous") {
    return (
      <div className="inline-flex items-center gap-2">
        <span className="inline-flex items-center rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-semibold text-slate-800 dark:bg-slate-800 dark:text-slate-200">
          {author.is_anonymous_op
            ? translate("identity.anonymousOp")
            : translate("identity.anonymousMember")}
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <a
        href={`/u/${encodeURIComponent(author.handle || "")}`}
        className="text-sm font-semibold text-slate-900 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-white"
      >
        {author.display_name}
      </a>
      {author.handle ? (
        <span className="text-xs text-slate-500 dark:text-slate-400">
          @{author.handle}
        </span>
      ) : null}
      {author.identity_mode === "professional" && author.professional_badge ? (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300 bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200">
          <span>
            {author.professional_badge.role_title} • {author.professional_badge.industry}
          </span>
          <span className="opacity-75">
            ({translate("identity.modes.professional.unverifiedBadge")})
          </span>
        </span>
      ) : null}
    </div>
  );
}
