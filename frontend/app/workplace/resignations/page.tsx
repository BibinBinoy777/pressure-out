"use client";

import React, { useState } from "react";
import { Container } from "../../../components/Container";
import { ResignationStoryComposer } from "../../../components/workplace/ResignationStoryComposer";
import { PostCard } from "../../../components/posts/PostCard";
import type { PublicPostResponse } from "../../../lib/api-client";
import { translate } from "../../../lib/i18n";

const SAMPLE_RESIGNATIONS: PublicPostResponse[] = [
  {
    id: "resign-post-01",
    community: { slug: "resignation-stories", name: "Resignation Stories" },
    post_type: "workplace_experience",
    identity_mode: "anonymous",
    author: {
      identity_mode: "anonymous",
      display_name: "Anonymous Member",
      handle: null,
      avatar_url: null,
      professional_badge: null,
      is_anonymous_op: false,
    },
    title: "മികച്ച അവസരത്തിനായി ജോലി രാജിവെച്ച അനുഭവം",
    body: "മൂന്ന് വർഷത്തെ കാത്തിരിപ്പിന് ശേഷം പുതിയൊരു കമ്പനിയിലേക്ക് മാറി.",
    content_language: "ml",
    tags: ["resignation", "career-growth"],
    workplace_detail: {
      experience_kind: "resignation_story",
      experience_category: "resignation",
      primary_resignation_reason: "better_opportunity",
      secondary_resignation_reason: "compensation",
      experience_band: "mid_3_6",
      industry_category: "technology",
      transition_outcome: "accepted_new_role",
      lesson_learned: "Never feel guilty about prioritizing your own career growth.",
      is_self_reported: true,
    },
    poll: null,
    stats: { score: 27, upvote_count: 27, downvote_count: 0, comment_count: 6, reaction_counts: { support: 14 } },
    viewer_context: { is_author: false, can_edit: false, can_delete: false },
    pii_warnings: [],
    created_at: "2026-10-30T01:15:00Z",
    updated_at: "2026-10-30T01:15:00Z",
  },
];

export default function ResignationStoriesPage() {
  const [selectedReason, setSelectedReason] = useState<string>("all");

  const filtered =
    selectedReason === "all"
      ? SAMPLE_RESIGNATIONS
      : SAMPLE_RESIGNATIONS.filter(
          (p) =>
            p.workplace_detail?.primary_resignation_reason === selectedReason
        );

  return (
    <Container className="space-y-8">
      <header className="space-y-2 border-b border-slate-200 pb-5 dark:border-slate-800">
        <h1 className="text-3xl font-extrabold text-slate-900 dark:text-white">
          {translate("workplace.resignationsTitle")}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {translate("workplace.resignationsSubtitle")}
        </p>
      </header>

      <ResignationStoryComposer />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-900 dark:text-white">
          Community Resignation Stories
        </h2>
        <select
          aria-label="Filter by resignation reason"
          value={selectedReason}
          onChange={(e) => setSelectedReason(e.target.value)}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold dark:border-slate-700 dark:bg-slate-900"
        >
          <option value="all">All Resignation Reasons</option>
          <option value="better_opportunity">Better Career Opportunity</option>
          <option value="compensation">Compensation</option>
          <option value="management_problems">Management Problems</option>
          <option value="work_life_balance">Work-Life Balance</option>
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
