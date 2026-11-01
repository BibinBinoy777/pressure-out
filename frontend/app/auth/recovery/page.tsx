"use client";

import React, { useState } from "react";
import { Container } from "../../../components/Container";
import { FormField } from "../../../components/FormField";
import { Button } from "../../../components/Button";
import { ErrorMessage } from "../../../components/ErrorMessage";
import { apiRequest } from "../../../lib/api-client";
import { translate } from "../../../lib/i18n";

export default function RecoveryPage() {
  const [handle, setHandle] = useState<string>("");
  const [codeOrToken, setCodeOrToken] = useState<string>("");
  const [newPassword, setNewPassword] = useState<string>("");
  const [completed, setCompleted] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    const res = await apiRequest<{ status: string }>(
      "/api/v1/auth/recovery/reset",
      "POST",
      {
        handle,
        recovery_code_or_token: codeOrToken,
        new_password: newPassword,
      }
    );
    if (!res.ok) {
      setErrorMsg(res.error.message);
      return;
    }
    setCompleted(true);
  };

  return (
    <Container className="max-w-lg space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
          {translate("auth.recoveryTitle")}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {translate("auth.recoverySubtitle")}
        </p>
      </div>

      {errorMsg ? <ErrorMessage title="Recovery Error" message={errorMsg} /> : null}

      {completed ? (
        <div role="status" className="rounded-xl border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-950">
          Password reset complete. All previous sessions have been revoked.
        </div>
      ) : (
        <form onSubmit={(e) => void handleReset(e)} className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <FormField id="rec-handle" label={translate("auth.handleLabel")}>
            <input
              id="rec-handle"
              type="text"
              required
              value={handle}
              onChange={(e) => setHandle(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </FormField>

          <FormField id="rec-code" label={translate("auth.recoveryCodeLabel")}>
            <input
              id="rec-code"
              type="text"
              required
              value={codeOrToken}
              onChange={(e) => setCodeOrToken(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </FormField>

          <FormField id="rec-new-pwd" label={translate("auth.newPasswordLabel")}>
            <input
              id="rec-new-pwd"
              type="password"
              required
              minLength={10}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </FormField>

          <Button type="submit" className="w-full">
            {translate("auth.submitRecovery")}
          </Button>
        </form>
      )}
    </Container>
  );
}
