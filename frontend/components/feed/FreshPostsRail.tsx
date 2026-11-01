import React from "react";
import type { PublicPostResponse } from "../../lib/api-client";
import { PostCard } from "../posts/PostCard";
import { translate } from "../../lib/i18n";

export interface FreshPostsRailProps {
  posts: PublicPostResponse[];
}

export function FreshPostsRail({ posts }: FreshPostsRailProps) {
  return (
    <section aria-labelledby="fresh-posts-heading" className="space-y-4">
      <div className="space-y-1">
        <h2
          id="fresh-posts-heading"
          className="text-lg font-bold text-slate-900 dark:text-white"
        >
          {translate("explore.freshPostsHeading")}
        </h2>
        <p className="text-xs text-slate-600 dark:text-slate-400">
          {translate("explore.freshPostsSubtitle")}
        </p>
      </div>

      <div className="space-y-4">
        {posts.map((p) => (
          <PostCard key={p.id} post={p} />
        ))}
      </div>
    </section>
  );
}
