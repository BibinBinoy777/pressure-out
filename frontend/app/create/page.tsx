"use client";

import React, { useState } from "react";
import { Container } from "../../components/Container";
import { FormField } from "../../components/FormField";
import { Button } from "../../components/Button";
import { IdentityModeSelector } from "../../components/identity/IdentityModeSelector";
import { PiiWarningAlert } from "../../components/posts/PiiWarningAlert";
import type { IdentityMode, PostType } from "../../lib/api-client";
import { translate } from "../../lib/i18n";

const POST_TYPES: PostType[] = [
  "discussion",
  "rant",
  "question",
  "story",
  "poll",
  "advice_request",
  "workplace_experience",
  "meme",
];

const LANGUAGES = ["en", "ml", "hi", "ta", "es", "mul", "und"];

export default function CreatePostPage() {
  const [communitySlug, setCommunitySlug] = useState<string>("workplace-rants");
  const [postType, setPostType] = useState<PostType>("discussion");
  const [identityMode, setIdentityMode] = useState<IdentityMode>("pseudonymous");
  const [contentLanguage, setContentLanguage] = useState<string>("en");
  const [title, setTitle] = useState<string>("");
  const [body, setBody] = useState<string>("");
  const [tagsInput, setTagsInput] = useState<string>("");
  const [pollOptions, setPollOptions] = useState<string[]>(["Option 1", "Option 2"]);
  const [piiError, setPiiError] = useState<{ code: string; message: string } | null>(null);

  const addPollOption = () => {
    if (pollOptions.length < 8) {
      setPollOptions([...pollOptions, `Option ${pollOptions.length + 1}`]);
    }
  };

  return (
    <Container className="max-w-3xl space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
          {translate("posts.composerTitle")}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {translate("posts.composerSubtitle")}
        </p>
      </div>

      {piiError ? (
        <PiiWarningAlert
          errorCode={piiError.code}
          message={piiError.message}
          onConfirmOverride={() => setPiiError(null)}
        />
      ) : null}

      <form className="space-y-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <IdentityModeSelector value={identityMode} onChange={setIdentityMode} />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <FormField id="post-community" label={translate("posts.communityLabel")}>
            <select
              id="post-community"
              value={communitySlug}
              onChange={(e) => setCommunitySlug(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            >
              <option value="workplace-rants">c/workplace-rants</option>
              <option value="corporate-memes">c/corporate-memes</option>
              <option value="career-advice">c/career-advice</option>
              <option value="it-software">c/it-software</option>
              <option value="salary-talk">c/salary-talk</option>
              <option value="freshers-corner">c/freshers-corner</option>
              <option value="resignation-stories">c/resignation-stories</option>
            </select>
          </FormField>

          <FormField id="post-type" label={translate("posts.postTypeLabel")}>
            <select
              id="post-type"
              value={postType}
              onChange={(e) => setPostType(e.target.value as PostType)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            >
              {POST_TYPES.map((pt) => (
                <option key={pt} value={pt}>
                  {translate(`posts.types.${pt}`)}
                </option>
              ))}
            </select>
          </FormField>

          <FormField id="post-language" label={translate("posts.languageLabel")}>
            <select
              id="post-language"
              value={contentLanguage}
              onChange={(e) => setContentLanguage(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            >
              {LANGUAGES.map((lang) => (
                <option key={lang} value={lang}>
                  {translate(`posts.languages.${lang}`)}
                </option>
              ))}
            </select>
          </FormField>
        </div>

        <FormField
          id="post-title"
          label={translate("posts.titleLabel")}
          hint={translate("posts.titleHint")}
        >
          <input
            id="post-title"
            type="text"
            required
            minLength={3}
            maxLength={220}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
        </FormField>

        <FormField
          id="post-body"
          label={translate("posts.bodyLabel")}
          hint={translate("posts.bodyHint")}
        >
          <textarea
            id="post-body"
            rows={6}
            required
            maxLength={15000}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
        </FormField>

        {postType === "poll" ? (
          <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-900 dark:text-white">
                {translate("posts.pollOptionsLabel")}
              </span>
              <Button variant="outline" onClick={addPollOption}>
                {translate("posts.addPollOptionButton")}
              </Button>
            </div>
            {pollOptions.map((opt, idx) => (
              <input
                key={idx}
                type="text"
                value={opt}
                onChange={(e) => {
                  const copy = [...pollOptions];
                  copy[idx] = e.target.value;
                  setPollOptions(copy);
                }}
                className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
              />
            ))}
          </div>
        ) : null}

        <FormField
          id="post-tags"
          label={translate("posts.tagsLabel")}
          hint={translate("posts.tagsHint")}
        >
          <input
            id="post-tags"
            type="text"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
        </FormField>

        <Button type="submit" className="w-full sm:w-auto">
          {translate("posts.publishButton")}
        </Button>
      </form>
    </Container>
  );
}
