"use client";

import React, { useState } from "react";
import { Container } from "../../../components/Container";
import { FormField } from "../../../components/FormField";
import { Button } from "../../../components/Button";
import { ErrorMessage } from "../../../components/ErrorMessage";
import { registerAccount } from "../../../lib/api-client";
import { translate } from "../../../lib/i18n";

export default function RegisterPage() {
  const [handle, setHandle] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [recoveryEmail, setRecoveryEmail] = useState<string>("");
  const [recoveryCode, setRecoveryCode] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<boolean>(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorMsg(null);
    const res = await registerAccount({
      handle,
      password,
      recovery_email: recoveryEmail.trim() || null,
    });
    setSubmitting(false);
    if (!res.ok) {
      setErrorMsg(res.error.message);
      return;
    }
    setRecoveryCode(res.data.one_time_recovery_code ?? null);
  };

  return (
    <Container className="max-w-lg space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
          {translate("auth.registerTitle")}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {translate("auth.registerSubtitle")}
        </p>
      </div>

      {errorMsg ? (
        <ErrorMessage title="Registration Error" message={errorMsg} />
      ) : null}

      {recoveryCode ? (
        <div
          role="region"
          aria-label={translate("auth.recoveryCodeNoticeTitle")}
          className="space-y-3 rounded-xl border border-emerald-300 bg-emerald-50 p-5 text-emerald-950 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-100"
        >
          <h2 className="text-base font-bold">
            {translate("auth.recoveryCodeNoticeTitle")}
          </h2>
          <p className="text-sm">{translate("auth.recoveryCodeNoticeBody")}</p>
          <p className="rounded-lg bg-white p-3 font-mono text-base font-bold tracking-wider text-slate-900 dark:bg-slate-900 dark:text-white">
            {recoveryCode}
          </p>
        </div>
      ) : (
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <FormField
            id="register-handle"
            label={translate("auth.handleLabel")}
            hint={translate("auth.handleHint")}
          >
            <input
              id="register-handle"
              type="text"
              required
              minLength={3}
              maxLength={32}
              value={handle}
              onChange={(e) => setHandle(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </FormField>

          <FormField
            id="register-password"
            label={translate("auth.passwordLabel")}
            hint={translate("auth.passwordHint")}
          >
            <input
              id="register-password"
              type="password"
              required
              minLength={10}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </FormField>

          <FormField
            id="register-email"
            label={translate("auth.recoveryEmailLabel")}
            hint={translate("auth.recoveryEmailHint")}
          >
            <input
              id="register-email"
              type="email"
              value={recoveryEmail}
              onChange={(e) => setRecoveryEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </FormField>

          <Button type="submit" disabled={submitting} className="w-full">
            {translate("auth.submitRegister")}
          </Button>
        </form>
      )}
    </Container>
  );
}
