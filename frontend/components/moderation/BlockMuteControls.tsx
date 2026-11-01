import React from "react";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface BlockMuteControlsProps {
  handle: string;
  currentMode?: "block" | "mute" | null;
  onChangeMode: (active: boolean, mode: "block" | "mute") => void;
}

export function BlockMuteControls({
  handle,
  currentMode = null,
  onChangeMode,
}: BlockMuteControlsProps) {
  return (
    <div
      role="group"
      aria-label={`Block or mute @${handle}`}
      className="flex flex-wrap items-center gap-2"
    >
      {currentMode === "mute" ? (
        <Button variant="outline" onClick={() => onChangeMode(false, "mute")}>
          {translate("moderation.unmuteButton")} @{handle}
        </Button>
      ) : (
        <Button variant="outline" onClick={() => onChangeMode(true, "mute")}>
          {translate("moderation.muteButton")}
        </Button>
      )}

      {currentMode === "block" ? (
        <Button variant="secondary" onClick={() => onChangeMode(false, "block")}>
          {translate("moderation.unblockButton")} @{handle}
        </Button>
      ) : (
        <Button variant="secondary" onClick={() => onChangeMode(true, "block")}>
          {translate("moderation.blockButton")}
        </Button>
      )}
    </div>
  );
}
