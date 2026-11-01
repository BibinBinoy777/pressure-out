import React from "react";
import type { IdentityMode, MemeAssetResponse } from "../../lib/api-client";
import { IdentityModeSelector } from "../identity/IdentityModeSelector";
import { FormField } from "../FormField";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface PublishMemeDialogProps {
  asset: MemeAssetResponse | null;
  communitySlug: string;
  identityMode: IdentityMode;
  title: string;
  body: string;
  tagsInput: string;
  hasProfessionalProfile?: boolean;
  isPublishing?: boolean;
  publishedPostId?: string | null;
  onCommunityChange: (slug: string) => void;
  onIdentityModeChange: (mode: IdentityMode) => void;
  onTitleChange: (title: string) => void;
  onBodyChange: (body: string) => void;
  onTagsChange: (tags: string) => void;
  onPublish: () => void;
}

const MEME_COMMUNITIES = [
  { slug: "corporate-memes", name: "c/corporate-memes — Corporate Memes" },
  { slug: "office-humour", name: "c/office-humour — Office Humour" },
  { slug: "workplace-rants", name: "c/workplace-rants — Workplace Rants" },
  { slug: "it-software", name: "c/it-software — IT & Software" },
  { slug: "general-workplace", name: "c/general-workplace — General Workplace" },
];

export function PublishMemeDialog({
  asset,
  communitySlug,
  identityMode,
  title,
  body,
  tagsInput,
  hasProfessionalProfile = false,
  isPublishing = false,
  publishedPostId = null,
  onCommunityChange,
  onIdentityModeChange,
  onTitleChange,
  onBodyChange,
  onTagsChange,
  onPublish,
}: PublishMemeDialogProps) {
  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-slate-900 dark:text-white">
          3. {translate("memeStudio.publishDialogHeading")}
        </h2>
        {asset ? (
          <span className="rounded-full bg-emerald-100 px-3 py-0.5 text-xs font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
            Asset Ready (#{asset.id.slice(0, 8)})
          </span>
        ) : (
          <span className="text-xs text-slate-500">
            Render a template meme or complete an AI image job first to unlock publishing.
          </span>
        )}
      </div>

      {publishedPostId ? (
        <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200">
          Meme post published to <strong>c/{communitySlug}</strong>!{" "}
          <a href={`/p/${encodeURIComponent(publishedPostId)}`} className="font-bold underline">
            View Published Meme Post →
          </a>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="meme-community-select" label={translate("posts.communityLabel")}>
          <select
            id="meme-community-select"
            value={communitySlug}
            onChange={(e) => onCommunityChange(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          >
            {MEME_COMMUNITIES.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.name}
              </option>
            ))}
          </select>
        </FormField>

        <FormField id="meme-tags-input" label={translate("posts.tagsLabel")}>
          <input
            id="meme-tags-input"
            type="text"
            value={tagsInput}
            onChange={(e) => onTagsChange(e.target.value)}
            placeholder="friday-deploy, standup, corporate-memes"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
        </FormField>
      </div>

      <IdentityModeSelector
        value={identityMode}
        onChange={onIdentityModeChange}
        hasProfessionalProfile={hasProfessionalProfile}
      />

      <FormField id="meme-post-title" label={translate("posts.titleLabel")}>
        <input
          id="meme-post-title"
          type="text"
          maxLength={220}
          value={title}
          onChange={(e) => onTitleChange(e.target.value)}
          placeholder="Give your workplace meme a relatable title..."
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
      </FormField>

      <FormField id="meme-post-body" label="Optional Post Context / Backstory">
        <textarea
          id="meme-post-body"
          rows={2}
          maxLength={4000}
          value={body}
          onChange={(e) => onBodyChange(e.target.value)}
          placeholder="Add optional context or story behind this meme..."
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
      </FormField>

      <div className="pt-2">
        <Button
          onClick={onPublish}
          disabled={!asset || isPublishing || title.trim().length < 3}
        >
          {isPublishing ? "Publishing..." : translate("memeStudio.publishButton")}
        </Button>
      </div>
    </section>
  );
}
