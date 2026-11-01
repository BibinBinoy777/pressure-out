import React from "react";
import type { PublicCommentResponse } from "../../lib/api-client";
import { CommentComposer } from "./CommentComposer";
import { CommentNode } from "./CommentNode";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface CommentThreadProps {
  comments: PublicCommentResponse[];
  totalCount: number;
  isAnonymousPostOp?: boolean;
  hasMore?: boolean;
  onLoadMore?: () => void;
}

export function CommentThread({
  comments,
  totalCount,
  isAnonymousPostOp = false,
  hasMore = false,
  onLoadMore,
}: CommentThreadProps) {
  return (
    <section aria-label="Comments" className="space-y-6">
      <h2 className="text-lg font-bold text-slate-900 dark:text-white">
        {translate("comments.sectionHeading", { count: totalCount })}
      </h2>

      <CommentComposer isAnonymousPostOp={isAnonymousPostOp} />

      {comments.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          {translate("comments.emptyThread")}
        </div>
      ) : (
        <div className="space-y-3">
          {comments.map((c) => (
            <CommentNode key={c.id} comment={c} />
          ))}
        </div>
      )}

      {hasMore && onLoadMore ? (
        <div className="flex justify-center">
          <Button variant="outline" onClick={onLoadMore}>
            {translate("comments.loadMoreButton")}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
