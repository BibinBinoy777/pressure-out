"use client";

import React, { useState } from "react";
import { Container } from "../../../components/Container";
import { WorkplaceExperienceComposer } from "../../../components/workplace/WorkplaceExperienceComposer";
import { PostCard } from "../../../components/posts/PostCard";
import type { PublicPostResponse } from "../../../lib/api-client";
import { translate } from "../../../lib/i18n";

const SAMPLE_EXPERIENCES: PublicPostResponse[] = [
  {
    id: "wx-post-01",
    community: { slug: "work-life-balance", name: "Work-Life Balance" },
    post_type: "workplace_experience",
    identity_mode: "pseudonymous",
    author: {
      identity_mode: "pseudonymous",
      display_name: "@kerala_tech_lead",
      handle: "kerala_tech_lead",
      avatar_url: null,
      professional_badge: null,
      is_anonymous_op: false,
    },
    title: "Switching to async-first updates cut our meeting load by half",
    body: "Replacing daily 45-minute status calls with written threads gave everyone uninterrupted morning focus.",
    content_language: "en",
    tags: ["remote-work", "work-life-balance"],
    workplace_detail: {
      experience_kind: "workplace_experience",
      experience_category: "remote_work",
      experience_band: "senior_6_10",
      industry_category: "technology",
      lesson_learned: "Protect deep work blocks by defaulting to async written updates.",
      is_self_reported: true,
    },
    poll: null,
    stats: { score: 19, upvote_count: 19, downvote_count: 0, comment_count: 4, reaction_counts: { relatable: 9 } },
    viewer_context: { is_author: false, can_edit: false, can_delete: false },
    pii_warnings: [],
    created_at: "2026-10-30T01:00:00Z",
    updated_at: "2026-10-30T01:00:00Z",
  },
];

export default function WorkplaceExperiencesPage() {
  const [selectedCategory, setSelectedCategory] = useState<string>("all");

  const filtered =
    selectedCategory === "all"
      ? SAMPLE_EXPERIENCES
      : SAMPLE_EXPERIENCES.filter(
          (p) => p.workplace_detail?.experience_category === selectedCategory
        );

  return (
    <Container className="space-y-8">
      <header className="space-y-2 border-b border-slate-200 pb-5 dark:border-slate-800">
        <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white">
          {translate("workplace.experiencesTitle")}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {translate("workplace.experiencesSubtitle")}
        </p>
      </header>

      <WorkplaceExperienceComposer />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-900 dark:text-white">
          Community Workplace Experiences
        </h2>
        <select
          aria-label="Filter by workplace experience category"
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold dark:border-slate-700 dark:bg-slate-900"
        >
          <option value="all">All Categories</option>
          <option value="remote_work">Remote & Hybrid Work</option>
          <option value="management">Management</option>
          <option value="work_life_balance">Work-Life Balance</option>
          <option value="compensation">Compensation</option>
        </select>
      </div>

      <div className="space-y-4">
        {filtered.map((post) => (
          <PostCard key={post.id} post={post} />
        ))}
      </div>
    </Container>
  );
}
