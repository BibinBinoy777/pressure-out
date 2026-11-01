"use client";

import React, { useState } from "react";
import type {
  DerivedTranslationResponse,
  PublicPostResponse,
  ReactionKind,
} from "../../lib/api-client";
import { AuthorBadge } from "../identity/AuthorBadge";
import { PollWidget } from "./PollWidget";
import { VoteControls } from "../engagement/VoteControls";
import { ReactionBar } from "../engagement/ReactionBar";
import { TranslateContentButton } from "../translations/TranslateContentButton";
import { TranslatedContent } from "../translations/TranslatedContent";
import { Button } from "../Button";
import { SupportedUiLocale, translate } from "../../lib/i18n";
import { detectTextDirection } from "../../lib/unicode";

export interface PostCardProps {
  post: PublicPostResponse;
  isSaved?: boolean;
  initialTranslation?: DerivedTranslationResponse | null;
  translationError?: string | null;
  onEdit?: (postId: string) => void;
  onDelete?: (postId: string) => void;
  onPollVote?: (postId: string, optionIds: string[]) => void;
  onVote?: (postId: string, value: 1 | -1 | 0) => void;
  onToggleReaction?: (postId: string, kind: ReactionKind, active: boolean) => void;
  onToggleSave?: (postId: string, nextSaved: boolean) => void;
  onReport?: (postId: string) => void;
  onTranslate?: (postId: string, targetLocale: SupportedUiLocale) => void;
}

export function PostCard({
  post,
  isSaved = false,
  initialTranslation = null,
  translationError = null,
  onEdit,
  onDelete,
  onPollVote,
  onVote,
  onToggleReaction,
  onToggleSave,
  onReport,
  onTranslate,
}: PostCardProps) {
  const [targetLocale, setTargetLocale] = useState<SupportedUiLocale>("en");
  const [translation, setTranslation] = useState<DerivedTranslationResponse | null>(
    initialTranslation
  );
  const [showTranslation, setShowTranslation] = useState<boolean>(
    Boolean(initialTranslation)
  );
  const contentDir = detectTextDirection(
    `${post.title} ${post.body}`,
    post.content_language
  );

  const handleRequestTranslation = (loc: SupportedUiLocale) => {
    if (onTranslate) {
      onTranslate(post.id, loc);
    }
    setShowTranslation(true);
    if (!translation) {
      setTranslation({
        id: `tr-${post.id}-${loc}`,
        source_type: "post",
        source_id: post.id,
        source_version_hash: "live_preview",
        source_language: post.content_language,
        source_language_label: post.content_language.toUpperCase(),
        is_source_language_uncertain:
          post.content_language === "mul" || post.content_language === "und",
        target_locale: loc,
        target_locale_label: loc.toUpperCase(),
        translated_title: `[${loc.toUpperCase()}] ${post.title}`,
        translated_body: `[${loc.toUpperCase()}] ${post.body}`,
        direction: detectTextDirection(post.body, loc),
        provenance_label: `Translated from ${post.content_language}`,
        provider_name: "local_mock",
        model_name: "po-mock-translate-v1",
        is_mock_provider: true,
        cache_hit: false,
        created_at: new Date().toISOString(),
      });
    }
  };

  return (
    <article className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
        <div className="flex flex-wrap items-center gap-2">
          <a
            href={`/c/${encodeURIComponent(post.community.slug)}`}
            className="font-semibold text-indigo-700 hover:underline dark:text-indigo-300"
          >
            c/{post.community.slug}
          </a>
          <span aria-hidden="true">•</span>
          <span className="rounded-md bg-slate-100 px-2 py-0.5 font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            {translate(`posts.types.${post.post_type}`)}
          </span>
          <span className="rounded-md border border-slate-200 px-1.5 py-0.5 font-mono uppercase dark:border-slate-700">
            {post.content_language}
          </span>
        </div>

        {post.viewer_context.is_author ? (
          <div className="flex items-center gap-2">
            {onEdit ? (
              <Button variant="outline" onClick={() => onEdit(post.id)}>
                {translate("posts.editButton")}
              </Button>
            ) : null}
            {onDelete ? (
              <Button variant="secondary" onClick={() => onDelete(post.id)}>
                {translate("posts.deleteButton")}
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>

      <AuthorBadge author={post.author} />

      <div className="space-y-2" dir={contentDir}>
        <h2 className="text-xl font-bold text-slate-900 dark:text-white">
          <a
            href={`/p/${encodeURIComponent(post.id)}`}
            className="hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            {post.title}
          </a>
        </h2>
        <p className="whitespace-pre-line text-sm leading-relaxed text-slate-700 dark:text-slate-300">
          {post.body}
        </p>
      </div>

      {post.workplace_detail ? (
        <div className="space-y-1.5 rounded-lg border border-indigo-100 bg-indigo-50/40 p-3 text-xs dark:border-indigo-900/50 dark:bg-indigo-950/30">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded bg-indigo-100 px-2 py-0.5 font-semibold text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200">
              {post.workplace_detail.experience_category.replace(/_/g, " ")}
            </span>
            {post.workplace_detail.primary_resignation_reason ? (
              <span className="rounded bg-amber-100 px-2 py-0.5 font-semibold text-amber-900 dark:bg-amber-900 dark:text-amber-200">
                Reason: {post.workplace_detail.primary_resignation_reason.replace(/_/g, " ")}
              </span>
            ) : null}
            <span className="text-[11px] text-slate-500">
              {translate("workplace.selfReportedBadge")}
            </span>
          </div>
          {post.workplace_detail.lesson_learned ? (
            <p className="italic text-slate-700 dark:text-slate-300">
              Takeaway: “{post.workplace_detail.lesson_learned}”
            </p>
          ) : null}
        </div>
      ) : null}

      <TranslatedContent
        translation={translation}
        isShowingTranslation={showTranslation}
        errorMessage={translationError}
        onShowOriginal={() => setShowTranslation(false)}
        onRetry={() => handleRequestTranslation(targetLocale)}
      />

      {post.meme_asset ? (
        <figure className="overflow-hidden rounded-xl border border-slate-200 bg-slate-950 p-2 dark:border-slate-800">
          <img
            src={post.meme_asset.download_url}
            alt={post.meme_asset.alt_text}
            width={post.meme_asset.width}
            height={post.meme_asset.height}
            className="mx-auto max-h-[520px] w-auto rounded-lg object-contain"
          />
          <figcaption className="mt-2 flex items-center justify-between px-2 text-xs text-slate-400">
            <span>{post.meme_asset.alt_text}</span>
            <a
              href={post.meme_asset.download_url}
              download
              className="font-semibold text-indigo-400 hover:underline"
            >
              Download
            </a>
          </figcaption>
        </figure>
      ) : null}

      {post.poll ? (
        <PollWidget
          poll={post.poll}
          onVote={
            onPollVote ? (optionIds) => onPollVote(post.id, optionIds) : undefined
          }
        />
      ) : null}

      {post.tags && post.tags.length > 0 ? (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {post.tags.map((tag) => (
            <span
              key={tag}
              className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300"
            >
              #{tag}
            </span>
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3 dark:border-slate-800">
        <div className="flex flex-wrap items-center gap-2">
          <VoteControls
            score={post.stats.score}
            onVote={onVote ? (val) => onVote(post.id, val) : undefined}
          />
          <ReactionBar
            reactionCounts={post.stats.reaction_counts}
            onToggleReaction={
              onToggleReaction
                ? (kind, active) => onToggleReaction(post.id, kind, active)
                : undefined
            }
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <TranslateContentButton
            sourceLanguage={post.content_language}
            targetLocale={targetLocale}
            isShowingTranslation={showTranslation}
            onTargetLocaleChange={setTargetLocale}
            onRequestTranslation={handleRequestTranslation}
            onToggleOriginal={() => setShowTranslation(false)}
          />
          {onToggleSave ? (
            <Button
              variant="outline"
              onClick={() => onToggleSave(post.id, !isSaved)}
            >
              {isSaved
                ? translate("engagement.savedPost")
                : translate("engagement.savePost")}
            </Button>
          ) : null}
          {onReport ? (
            <Button variant="outline" onClick={() => onReport(post.id)}>
              {translate("moderation.reportButton")}
            </Button>
          ) : null}
        </div>
      </div>
    </article>
  );
}
