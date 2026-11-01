import React from "react";
import type { MemeAssetResponse } from "../../lib/api-client";
import { translate } from "../../lib/i18n";

export interface MemeDownloadButtonProps {
  asset: MemeAssetResponse | null;
}

export function MemeDownloadButton({ asset }: MemeDownloadButtonProps) {
  if (!asset) return null;

  return (
    <a
      href={asset.download_url}
      download={`pressure-out-meme-${asset.id.slice(0, 8)}.png`}
      className="inline-flex items-center justify-center rounded-lg border border-indigo-600 bg-white px-4 py-2 text-sm font-semibold text-indigo-700 shadow-sm hover:bg-indigo-50 dark:border-indigo-400 dark:bg-slate-900 dark:text-indigo-300"
    >
      {translate("memeStudio.downloadButton")} ({asset.mime_type.split("/")[1]?.toUpperCase()})
    </a>
  );
}
