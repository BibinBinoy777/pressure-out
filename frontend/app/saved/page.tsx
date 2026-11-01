import React from "react";
import { Container } from "../../components/Container";
import { PostCard } from "../../components/posts/PostCard";
import type { PublicPostResponse } from "../../lib/api-client";
import { translate } from "../../lib/i18n";

export interface SavedPostsPageProps {
  initialPosts?: PublicPostResponse[];
}

export default function SavedPostsPage({ initialPosts }: SavedPostsPageProps) {
  const posts = initialPosts ?? [];

  return (
    <Container className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
        {translate("notifications.savedPageTitle")}
      </h1>

      {posts.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          {translate("notifications.savedEmptyMessage")}
        </div>
      ) : (
        <div className="space-y-4">
          {posts.map((p) => (
            <PostCard key={p.id} post={p} isSaved />
          ))}
        </div>
      )}
    </Container>
  );
}
