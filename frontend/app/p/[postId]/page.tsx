import React from "react";
import { Container } from "../../../components/Container";
import { PostCard } from "../../../components/posts/PostCard";
import { CommentThread } from "../../../components/comments/CommentThread";
import type { PublicCommentResponse, PublicPostResponse } from "../../../lib/api-client";

export interface PostDetailPageProps {
  params?: { postId?: string };
  initialPost?: PublicPostResponse;
  initialComments?: PublicCommentResponse[];
}

export default function PostDetailPage({
  params,
  initialPost,
  initialComments,
}: PostDetailPageProps) {
  const postId = params?.postId ?? "sample-post";
  const post: PublicPostResponse = initialPost ?? {
    id: postId,
    community: { slug: "workplace-rants", name: "Workplace Rants" },
    post_type: "discussion",
    identity_mode: "anonymous",
    author: {
      identity_mode: "anonymous",
      display_name: "Anonymous Member",
      handle: null,
      avatar_url: null,
      professional_badge: null,
      is_anonymous_op: false,
    },
    title: "Workplace Conversation Thread",
    body: "Post detail view with nested discussion replies.",
    content_language: "en",
    tags: ["workplace"],
    stats: {
      score: 12,
      upvote_count: 13,
      downvote_count: 1,
      comment_count: 1,
      reaction_counts: { relatable: 4 },
    },
    viewer_context: {
      is_author: true,
      can_edit: true,
      can_delete: true,
    },
    pii_warnings: [],
    created_at: "2026-10-29T00:00:00Z",
    updated_at: "2026-10-29T00:00:00Z",
  };

  const comments: PublicCommentResponse[] = initialComments ?? [];
  const isAnonymousPostOp =
    post.viewer_context.is_author && post.identity_mode === "anonymous";

  return (
    <Container className="max-w-3xl space-y-8">
      <PostCard post={post} />
      <CommentThread
        comments={comments}
        totalCount={post.stats.comment_count}
        isAnonymousPostOp={isAnonymousPostOp}
      />
    </Container>
  );
}
