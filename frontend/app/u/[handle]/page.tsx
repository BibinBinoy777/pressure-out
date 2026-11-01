"use client";

import React, { useState } from "react";
import { Container } from "../../../components/Container";
import { Button } from "../../../components/Button";
import { BlockMuteControls } from "../../../components/moderation/BlockMuteControls";
import { ReportModal } from "../../../components/moderation/ReportModal";
import type { ReportReasonCode } from "../../../lib/api-client";
import { translate } from "../../../lib/i18n";

export interface PublicProfilePageProps {
  params?: { handle?: string };
}

export default function PublicProfilePage({ params }: PublicProfilePageProps) {
  const handle = params?.handle ?? "member";
  const [blockMode, setBlockMode] = useState<"block" | "mute" | null>(null);
  const [reportOpen, setReportOpen] = useState<boolean>(false);
  const [reason, setReason] = useState<ReportReasonCode>("impersonation");
  const [details, setDetails] = useState<string>("");
  const [submitted, setSubmitted] = useState<boolean>(false);

  return (
    <Container className="max-w-3xl space-y-6">
      <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
              @{handle}
            </h1>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {translate("identity.modes.anonymous.description")}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <BlockMuteControls
              handle={handle}
              currentMode={blockMode}
              onChangeMode={(active, mode) =>
                setBlockMode(active ? mode : null)
              }
            />
            <Button variant="outline" onClick={() => setReportOpen(true)}>
              {translate("moderation.reportButton")} Profile
            </Button>
          </div>
        </div>
      </section>

      <ReportModal
        isOpen={reportOpen}
        targetType="profile"
        targetId={handle}
        selectedReason={reason}
        details={details}
        isSubmitted={submitted}
        onReasonChange={setReason}
        onDetailsChange={setDetails}
        onSubmit={() => setSubmitted(true)}
        onClose={() => {
          setReportOpen(false);
          setSubmitted(false);
        }}
      />
    </Container>
  );
}
