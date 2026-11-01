"use client";

import React, { useState } from "react";
import type { IdentityMode } from "../../lib/api-client";
import { IdentityModeSelector } from "../identity/IdentityModeSelector";
import { AnonymousOpLockBanner } from "./AnonymousOpLockBanner";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface CommentComposerProps {
  isAnonymousPostOp?: boolean;
  parentCommentId?: string | null;
  onSubmit?: (payload: {
    body: string;
    identity_mode: IdentityMode;
    confirm_op_identity_reveal: boolean;
    parent_comment_id?: string | null;
  }) => void;
}

export function CommentComposer({
  isAnonymousPostOp = false,
  parentCommentId = null,
  onSubmit,
}: CommentComposerProps) {
  const [body, setBody] = useState<string>("");
  const [opUnlocked, setOpUnlocked] = useState<boolean>(false);
  const [selectedMode, setSelectedMode] = useState<IdentityMode>(
    isAnonymousPostOp ? "anonymous" : "pseudonymous"
  );

  const effectiveMode: IdentityMode =
    isAnonymousPostOp && !opUnlocked ? "anonymous" : selectedMode;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!body.trim() || !onSubmit) return;
    onSubmit({
      body,
      identity_mode: effectiveMode,
      confirm_op_identity_reveal: isAnonymousPostOp && opUnlocked,
      parent_comment_id: parentCommentId,
    });
    setBody("");
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
    >
      {isAnonymousPostOp ? (
        <AnonymousOpLockBanner
          unlocked={opUnlocked}
          onToggleUnlock={(next) => {
            setOpUnlocked(next);
            if (!next) {
              setSelectedMode("anonymous");
            }
          }}
        />
      ) : null}

      <IdentityModeSelector
        value={effectiveMode}
        onChange={setSelectedMode}
        disabled={isAnonymousPostOp && !opUnlocked}
      />

      <div>
        <label htmlFor="comment-body-input" className="sr-only">
          {translate("comments.composerPlaceholder")}
        </label>
        <textarea
          id="comment-body-input"
          rows={3}
          required
          maxLength={5000}
          placeholder={translate("comments.composerPlaceholder")}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        />
      </div>

      <div className="flex justify-end">
        <Button type="submit">{translate("comments.submitButton")}</Button>
      </div>
    </form>
  );
}
