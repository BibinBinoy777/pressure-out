import React from "react";
import type { AuditEventResponse } from "../../lib/api-client";

export interface AuditEventTableProps {
  events: AuditEventResponse[];
}

export function AuditEventTable({ events }: AuditEventTableProps) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <table className="w-full text-left text-xs">
        <thead className="border-b border-slate-200 bg-slate-50 font-semibold uppercase text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
          <tr>
            <th className="px-4 py-3">Timestamp (UTC)</th>
            <th className="px-4 py-3">Category</th>
            <th className="px-4 py-3">Action</th>
            <th className="px-4 py-3">Actor Role</th>
            <th className="px-4 py-3">Target</th>
            <th className="px-4 py-3">Reason Code</th>
            <th className="px-4 py-3">Redacted Metadata</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {events.map((ev) => (
            <tr key={ev.id}>
              <td className="whitespace-nowrap px-4 py-3 font-mono text-slate-500">
                {ev.created_at}
              </td>
              <td className="px-4 py-3 font-medium text-slate-900 dark:text-white">
                {ev.event_category}
              </td>
              <td className="px-4 py-3 font-mono text-indigo-700 dark:text-indigo-300">
                {ev.action_name}
              </td>
              <td className="px-4 py-3">{ev.actor_role}</td>
              <td className="px-4 py-3 font-mono">
                {ev.target_type}:{ev.target_id ? ev.target_id.slice(0, 8) : "n/a"}
              </td>
              <td className="px-4 py-3 font-mono">{ev.reason_code}</td>
              <td className="px-4 py-3 font-mono text-[11px] text-slate-600 dark:text-slate-400">
                {JSON.stringify(ev.redacted_metadata)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
