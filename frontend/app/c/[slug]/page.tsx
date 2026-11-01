import React from "react";
import { Container } from "../../../components/Container";
import { CommunityRulesList } from "../../../components/communities/CommunityRulesList";
import { PostCard } from "../../../components/posts/PostCard";
import type { CommunityDetailResponse, PublicPostResponse } from "../../../lib/api-client";
import { translate } from "../../../lib/i18n";

export interface CommunityPageProps {
  params?: { slug?: string };
  initialCommunity?: CommunityDetailResponse;
  initialPosts?: PublicPostResponse[];
}

export default function CommunityDetailPage({
  params,
  initialCommunity,
  initialPosts,
}: CommunityPageProps) {
  const slug = params?.slug ?? "workplace-rants";
  const community: CommunityDetailResponse = initialCommunity ?? {
    id: "comm_default",
    slug,
    name: slug.replace(/-/g, " ").replace(/\b\w/g, (l) => l.toUpperCase()),
    description:
      "Topic-based workplace community space with per-post identity control and responsible moderation.",
    primary_language: "en",
    status: "active",
    member_count: 42,
    post_count: 1,
    viewer_context: {
      is_member: true,
      role: "member",
      is_banned: false,
      can_post: true,
      can_moderate: false,
    },
    rules: [
      {
        rule_number: 1,
        title: "No Doxxing or Private Contact Information",
        description:
          "Never post personal phone numbers, email addresses, or identify non-public coworkers by full name.",
      },
      {
        rule_number: 2,
        title: "Respect Multilingual & Honest Expression",
        description:
          "Posts in English, regional languages, and mixed code-switched scripts are welcome.",
      },
    ],
    created_at: "2026-10-29T00:00:00Z",
  };

  const posts: PublicPostResponse[] = initialPosts ?? [];

  return (
    <Container className="space-y-8">
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white">
                {community.name}
              </h1>
              <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-semibold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                c/{community.slug}
              </span>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              {community.description}
            </p>
          </div>

          {community.viewer_context.can_post ? (
            <a
              href="/create"
              className="inline-flex shrink-0 items-center justify-center rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
            >
              {translate("communities.createPostInCommunity", {
                slug: community.slug,
              })}
            </a>
          ) : null}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {posts.length === 0 ? (
            <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
              {translate("communities.emptyFeedMessage")}
            </div>
          ) : (
            posts.map((p) => <PostCard key={p.id} post={p} />)
          )}
        </div>

        <div className="lg:col-span-1">
          <CommunityRulesList rules={community.rules} />
        </div>
      </div>
    </Container>
  );
}
