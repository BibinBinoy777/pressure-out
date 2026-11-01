"use client";

import React, { useState } from "react";
import { Container } from "../../components/Container";
import { CommunityCard } from "../../components/communities/CommunityCard";
import { FreshPostsRail } from "../../components/feed/FreshPostsRail";
import { Button } from "../../components/Button";
import type {
  CommunitySummaryResponse,
  PublicPostResponse,
  TrendingTagItem,
} from "../../lib/api-client";
import { translate } from "../../lib/i18n";

const SAMPLE_TAGS: TrendingTagItem[] = [
  { slug: "burnout", display_name: "burnout", usage_count: 42, viewer_preference: null },
  { slug: "appraisal", display_name: "appraisal", usage_count: 37, viewer_preference: "follow" },
  { slug: "wfh", display_name: "wfh", usage_count: 29, viewer_preference: null },
  { slug: "standup", display_name: "standup", usage_count: 24, viewer_preference: null },
];

export interface ExplorePageProps {
  initialTags?: TrendingTagItem[];
  initialCommunities?: CommunitySummaryResponse[];
  initialFreshPosts?: PublicPostResponse[];
}

export default function ExplorePage({
  initialTags,
  initialCommunities,
  initialFreshPosts,
}: ExplorePageProps) {
  const [tags, setTags] = useState<TrendingTagItem[]>(initialTags ?? SAMPLE_TAGS);
  const communities = initialCommunities ?? [];
  const freshPosts = initialFreshPosts ?? [];

  const togglePref = (slug: string, pref: "follow" | "mute") => {
    setTags((prev) =>
      prev.map((t) =>
        t.slug === slug
          ? {
              ...t,
              viewer_preference: t.viewer_preference === pref ? null : pref,
            }
          : t
      )
    );
  };

  return (
    <Container className="space-y-10">
      <div className="space-y-2">
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
          {translate("explore.pageTitle")}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {translate("explore.pageSubtitle")}
        </p>
      </div>

      {/* Trending Tags with Follow / Mute Topic Controls */}
      <section aria-labelledby="trending-tags-heading" className="space-y-4">
        <h2
          id="trending-tags-heading"
          className="text-lg font-bold text-slate-900 dark:text-white"
        >
          {translate("explore.trendingTagsHeading")}
        </h2>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {tags.map((tag) => (
            <div
              key={tag.slug}
              className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
            >
              <div>
                <p className="font-bold text-slate-900 dark:text-white">
                  #{tag.display_name}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {tag.usage_count} posts
                </p>
              </div>

              <div className="mt-3 flex items-center gap-2">
                <Button
                  variant={tag.viewer_preference === "follow" ? "primary" : "outline"}
                  onClick={() => togglePref(tag.slug, "follow")}
                >
                  {translate("explore.followTagButton")}
                </Button>
                <Button
                  variant={tag.viewer_preference === "mute" ? "secondary" : "outline"}
                  onClick={() => togglePref(tag.slug, "mute")}
                >
                  {translate("explore.muteTagButton")}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {communities.length > 0 ? (
        <section className="space-y-4">
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            {translate("explore.featuredCommunitiesHeading")}
          </h2>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            {communities.map((c) => (
              <CommunityCard key={c.slug} community={c} />
            ))}
          </div>
        </section>
      ) : null}

      <FreshPostsRail posts={freshPosts} />
    </Container>
  );
}
