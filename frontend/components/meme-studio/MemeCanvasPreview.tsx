import React from "react";
import type { MemeAssetResponse, MemeTemplateResponse } from "../../lib/api-client";

export interface MemeCanvasPreviewProps {
  template: MemeTemplateResponse;
  captionValues: Record<string, string>;
  renderedAsset?: MemeAssetResponse | null;
}

export function MemeCanvasPreview({
  template,
  captionValues,
  renderedAsset,
}: MemeCanvasPreviewProps) {
  const topText = captionValues["top"] || "TOP CAPTION PREVIEW";
  const bottomText = captionValues["bottom"] || "BOTTOM CAPTION PREVIEW";

  return (
    <section
      aria-label="Meme live preview"
      className="space-y-3 rounded-xl border border-slate-200 bg-slate-900 p-5 text-white shadow-sm dark:border-slate-800"
    >
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span className="font-semibold uppercase tracking-wider text-indigo-400">
          {renderedAsset ? "Validated Server Render" : "Live Studio Preview"}
        </span>
        <span>
          {template.width}×{template.height}px ({template.aspect_ratio})
        </span>
      </div>

      {renderedAsset ? (
        <div className="space-y-2">
          <img
            src={renderedAsset.download_url}
            alt={renderedAsset.alt_text}
            width={renderedAsset.width}
            height={renderedAsset.height}
            className="mx-auto max-h-[420px] w-auto rounded-lg border border-slate-700 object-contain"
          />
          <p className="text-center text-xs text-emerald-400">
            Rendered {renderedAsset.mime_type.toUpperCase()} ({Math.round(renderedAsset.file_size_bytes / 1024)} KB) • SHA-256 Verified
          </p>
        </div>
      ) : (
        <div className="flex min-h-[320px] flex-col justify-between rounded-xl border-2 border-indigo-500/40 bg-gradient-to-b from-slate-900 via-indigo-950 to-slate-950 p-6 text-center">
          <p className="break-words text-lg font-extrabold tracking-wide text-white drop-shadow">
            {topText}
          </p>
          <div className="my-4 rounded-lg border border-orange-500/50 bg-slate-900/90 px-4 py-2 text-xs font-semibold uppercase tracking-widest text-orange-400">
            {template.name}
          </div>
          <p className="break-words text-lg font-extrabold tracking-wide text-white drop-shadow">
            {bottomText}
          </p>
        </div>
      )}

      <p className="text-[11px] text-slate-400">
        License: {template.license_info}
      </p>
    </section>
  );
}
