"use client";

import React, { useState } from "react";
import type {
  DerivedTranslationResponse,
  PublicCommentResponse,
  ReactionKind,
} from "../../lib/api-client";
import { AuthorBadge } from "../identity/AuthorBadge";
import { VoteControls } from "../engagement/VoteControls";
import { ReactionBar } from "../engagement/ReactionBar";
import { TranslateContentButton } from "../translations/TranslateContentButton";
import { TranslatedContent } from "../translations/TranslatedContent";
import { Button } from "../Button";
import { SupportedUiLocale, translate } from "../../lib/i18n";
import { detectTextDirection } from "../../lib/unicode";

export interface CommentNodeProps {
  comment: PublicCommentResponse;
  initialTranslation?: DerivedTranslationResponse | null;
  onReplyClick?: (commentId: string) => void;
  onDeleteClick?: (commentId: string) => void;
  onReportClick?: (commentId: string) => void;
  onVote?: (commentId: string, value: 1 | -1 | 0) => void;
  onToggleReaction?: (commentId: string, kind: ReactionKind, active: boolean) => void;
}

export function CommentNode({
  comment,
  initialTranslation = null,
  onReplyClick,
  onDeleteClick,
  onReportClick,
  onVote,
  onToggleReaction,
}: CommentNodeProps) {
  const indentLevel = Math.min(comment.depth, 6);
  const [targetLocale, setTargetLocale] = useState<SupportedUiLocale>("en");
  const [translation, setTranslation] = useState<DerivedTranslationResponse | null>(
    initialTranslation
  );
  const [showTranslation, setShowTranslation] = useState<boolean>(
    Boolean(initialTranslation)
  );
  const commentDir = detectTextDirection(comment.body, comment.content_language);

  return (
    <div
      style={{ marginLeft: `${indentLevel * 1.25}rem` }}
      className="space-y-2.5 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex items-center justify-between gap-2">
        <AuthorBadge author={comment.author} />
        <span className="rounded border border-slate-200 px-1.5 py-0.5 font-mono text-xs uppercase text-slate-500 dark:border-slate-700">
          {comment.content_language}
        </span>
      </div>

      <p
        dir={commentDir}
        className="whitespace-pre-line text-sm leading-relaxed text-slate-800 dark:text-slate-200"
      >
        {comment.body}
      </p>

      <TranslatedContent
        translation={translation}
        isShowingTranslation={showTranslation}
        onShowOriginal={() => setShowTranslation(false)}
      />

      {!comment.is_deleted ? (
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
          <div className="flex flex-wrap items-center gap-2">
            <VoteControls
              score={comment.stats.score}
              viewerVote={comment.viewer_context.viewer_vote}
              onVote={
                onVote ? (val) => onVote(comment.id, val) : undefined
              }
            />
            <ReactionBar
              reactionCounts={comment.stats.reaction_counts}
              viewerReactions={comment.viewer_context.viewer_reactions}
              onToggleReaction={
                onToggleReaction
                  ? (kind, active) => onToggleReaction(comment.id, kind, active)
                  : undefined
              }
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <TranslateContentButton
              sourceLanguage={comment.content_language}
              targetLocale={targetLocale}
              isShowingTranslation={showTranslation}
              onTargetLocaleChange={setTargetLocale}
              onRequestTranslation={(loc) => {
                setShowTranslation(true);
                if (!translation) {
                  setTranslation({
                    id: `tr-comm-${comment.id}-${loc}`,
                    source_type: "comment",
                    source_id: comment.id,
                    source_version_hash: "live_preview",
                    source_language: comment.content_language,
                    source_language_label: comment.content_language.toUpperCase(),
                    is_source_language_uncertain:
                      comment.content_language === "mul" ||
                      comment.content_language === "und",
                    target_locale: loc,
                    target_locale_label: loc.toUpperCase(),
                    translated_title: null,
                    translated_body: `[${loc.toUpperCase()}] ${comment.body}`,
                    direction: detectTextDirection(comment.body, loc),
                    provenance_label: `Translated from ${comment.content_language}`,
                    provider_name: "local_mock",
                    model_name: "po-mock-translate-v1",
                    is_mock_provider: true,
                    cache_hit: false,
                    created_at: new Date().toISOString(),
                  });
                }
              }}
              onToggleOriginal={() => setShowTranslation(false)}
            />
            {onReportClick ? (
              <Button
                variant="outline"
                onClick={() => onReportClick(comment.id)}
              >
                {translate("moderation.reportButton")}
              </Button>
            ) : null}
            {onReplyClick ? (
              <Button
                variant="outline"
                onClick={() => onReplyClick(comment.id)}
              >
                {translate("comments.replyButton")}
              </Button>
            ) : null}
            {comment.viewer_context.can_delete && onDeleteClick ? (
              <Button
                variant="secondary"
                onClick={() => onDeleteClick(comment.id)}
              >
                {translate("comments.deleteButton")}
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
