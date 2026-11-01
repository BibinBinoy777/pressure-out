"use client";

import React, { useState } from "react";
import { Container } from "../../components/Container";
import { Button } from "../../components/Button";
import type { NotificationResponse } from "../../lib/api-client";
import { translate } from "../../lib/i18n";

export interface NotificationsPageProps {
  initialNotifications?: NotificationResponse[];
}

export default function NotificationsPage({
  initialNotifications,
}: NotificationsPageProps) {
  const [items, setItems] = useState<NotificationResponse[]>(
    initialNotifications ?? []
  );

  const unreadCount = items.filter((n) => !n.is_read).length;

  const markAllRead = () => {
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
  };

  return (
    <Container className="max-w-3xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
            {translate("notifications.pageTitle")}
          </h1>
          <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-semibold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
            {translate("notifications.unreadBadge", { count: unreadCount })}
          </span>
        </div>

        <Button variant="outline" onClick={markAllRead} disabled={unreadCount === 0}>
          {translate("notifications.markAllReadButton")}
        </Button>
      </div>

      {items.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          {translate("notifications.emptyMessage")}
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((n) => (
            <li
              key={n.id}
              className={`rounded-xl border p-4 ${
                n.is_read
                  ? "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
                  : "border-indigo-300 bg-indigo-50/40 dark:border-indigo-800 dark:bg-indigo-950/30"
              }`}
            >
              <p className="text-sm font-semibold text-slate-900 dark:text-white">
                {n.title}
              </p>
              {n.body_preview ? (
                <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
                  {n.body_preview}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Container>
  );
}
