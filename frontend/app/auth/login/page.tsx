"use client";

import React, { useState } from "react";
import { Container } from "../../../components/Container";
import { FormField } from "../../../components/FormField";
import { Button } from "../../../components/Button";
import { ErrorMessage } from "../../../components/ErrorMessage";
import { loginAccount } from "../../../lib/api-client";
import { translate } from "../../../lib/i18n";

export default function LoginPage() {
  const [handle, setHandle] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [signedInHandle, setSignedInHandle] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<boolean>(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErrorMsg(null);
    const res = await loginAccount({ handle, password });
    setSubmitting(false);
    if (!res.ok) {
      setErrorMsg(res.error.message);
      return;
    }
    setSignedInHandle(res.data.handle);
  };

  return (
    <Container className="max-w-lg space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
          {translate("auth.loginTitle")}
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {translate("auth.loginSubtitle")}
        </p>
      </div>

      {errorMsg ? <ErrorMessage title="Sign-In Failed" message={errorMsg} /> : null}

      {signedInHandle ? (
        <div role="status" className="rounded-xl border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-950 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-100">
          Signed in as <strong>@{signedInHandle}</strong>.
        </div>
      ) : (
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <FormField id="login-handle" label={translate("auth.handleLabel")}>
            <input
              id="login-handle"
              type="text"
              required
              value={handle}
              onChange={(e) => setHandle(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </FormField>

          <FormField id="login-password" label={translate("auth.passwordLabel")}>
            <input
              id="login-password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </FormField>

          <Button type="submit" disabled={submitting} className="w-full">
            {translate("auth.submitLogin")}
          </Button>
        </form>
      )}
    </Container>
  );
}
