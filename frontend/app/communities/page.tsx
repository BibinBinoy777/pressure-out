"use client";

import React, { useState } from "react";
import { Container } from "../../components/Container";
import { CommunityCard } from "../../components/communities/CommunityCard";
import type { CommunitySummaryResponse } from "../../lib/api-client";
import { translate } from "../../lib/i18n";

const DEFAULT_DIRECTORY: CommunitySummaryResponse[] = [
  {
    id: "comm_1",
    slug: "workplace-rants",
    name: "Workplace Rants",
    description:
      "Unfiltered vents about micromanagement, pointless meetings, scope creep, and daily office chaos.",
    icon_name: "flame",
    primary_language: "en",
    status: "active",
    member_count: 142,
    post_count: 38,
    viewer_context: { is_member: false, is_banned: false, can_post: true, can_moderate: false },
  },
  {
    id: "comm_2",
    slug: "corporate-memes",
    name: "Corporate Memes",
    description:
      "Visual humour, standup comedy, sprint retro memes, and AI Meme Studio creations about working life.",
    icon_name: "laugh",
    primary_language: "en",
    status: "active",
    member_count: 215,
    post_count: 64,
    viewer_context: { is_member: true, is_banned: false, can_post: true, can_moderate: false },
  },
  {
    id: "comm_3",
    slug: "salary-talk",
    name: "Salary Talk",
    description:
      "Candid conversations about compensation bands, appraisals, bonuses, and offer negotiations.",
    icon_name: "banknote",
    primary_language: "en",
    status: "active",
    member_count: 189,
    post_count: 41,
    viewer_context: { is_member: false, is_banned: false, can_post: true, can_moderate: false },
  },
  {
    id: "comm_4",
    slug: "freshers-corner",
    name: "Freshers' Corner",
    description:
      "A welcoming space for recent graduates, interns, and first-time employees learning workplace survival.",
    icon_name: "sparkles",
    primary_language: "en",
    status: "active",
    member_count: 96,
    post_count: 19,
    viewer_context: { is_member: false, is_banned: false, can_post: true, can_moderate: false },
  },
];

export default function CommunitiesDirectoryPage() {
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [communities, setCommunities] =
    useState<CommunitySummaryResponse[]>(DEFAULT_DIRECTORY);

  const filtered = communities.filter((c) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      c.name.toLowerCase().includes(q) ||
      c.slug.toLowerCase().includes(q) ||
      c.description.toLowerCase().includes(q)
    );
  });

  const handleToggleMembership = (slug: string, action: "join" | "leave") => {
    setCommunities((prev) =>
      prev.map((c) =>
        c.slug === slug
          ? {
              ...c,
              member_count:
                action === "join" ? c.member_count + 1 : Math.max(0, c.member_count - 1),
              viewer_context: { ...c.viewer_context, is_member: action === "join" },
            }
          : c
      )
    );
  };

  return (
    <Container className="space-y-8">
      <div className="space-y-2">
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
          {translate("communities.directoryTitle")}
        </h1>
        <p className="max-w-2xl text-sm text-slate-600 dark:text-slate-400">
          {translate("communities.directorySubtitle")}
        </p>
      </div>

      <div>
        <label htmlFor="community-search" className="sr-only">
          {translate("communities.searchPlaceholder")}
        </label>
        <input
          id="community-search"
          type="search"
          placeholder={translate("communities.searchPlaceholder")}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full max-w-md rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm dark:border-slate-700 dark:bg-slate-900"
        />
      </div>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {filtered.map((comm) => (
          <CommunityCard
            key={comm.slug}
            community={comm}
            onToggleMembership={handleToggleMembership}
          />
        ))}
      </div>
    </Container>
  );
}
