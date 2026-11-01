import React from "react";
import { Button } from "../Button";
import { translate } from "../../lib/i18n";

export interface PiiWarningAlertProps {
  errorCode: string;
  message: string;
  suggestion?: string;
  onConfirmOverride?: () => void;
}

export function PiiWarningAlert({
  errorCode,
  message,
  suggestion,
  onConfirmOverride,
}: PiiWarningAlertProps) {
  const isConfirmationRequired = errorCode === "PII_CONFIRMATION_REQUIRED";

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`rounded-xl border p-4 ${
        isConfirmationRequired
          ? "border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100"
          : "border-red-300 bg-red-50 text-red-950 dark:border-red-800 dark:bg-red-950/40 dark:text-red-100"
      }`}
    >
      <div className="space-y-2">
        <h3 className="text-sm font-bold">
          {isConfirmationRequired
            ? translate("posts.piiSoftWarningTitle")
            : translate("posts.piiHardBlockTitle")}
        </h3>
        <p className="text-sm">{message}</p>
        {suggestion ? (
          <p className="text-xs opacity-90">{suggestion}</p>
        ) : null}
        {isConfirmationRequired && onConfirmOverride ? (
          <div className="pt-2">
            <Button variant="secondary" onClick={onConfirmOverride}>
              {translate("posts.piiConfirmButton")}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
