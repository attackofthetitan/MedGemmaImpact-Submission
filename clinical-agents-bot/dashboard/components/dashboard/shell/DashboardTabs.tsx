"use client";

import { memo } from "react";
import { OverviewTab } from "@/features/overview/components/OverviewTab";
import { EhrCreateTab } from "@/features/ehr-create/components/EhrCreateTab";
import { UserAccessTab } from "@/features/user-access/components/UserAccessTab";
import { UserManagementTab } from "@/features/user-management/components/UserManagementTab";
import { RagTab } from "@/features/rag/components/RagTab";
import { SessionTicketsTab } from "@/features/session-tickets/components/SessionTicketsTab";
import { LineBindingTab } from "@/features/line-binding/components/LineBindingTab";

export type Tab = "overview" | "ehr-create" | "user-access" | "user-management" | "session-tickets" | "line-binding" | "rag";

export function DashboardTabPanel({ tab, visibleTabs }: { tab: Tab; visibleTabs: Tab[] }) {
  if (!visibleTabs.includes(tab)) return null;
  switch (tab) {
    case "overview":
      return <OverviewTab />;
    case "ehr-create":
      return <EhrCreateTab />;
    case "user-access":
      return <UserAccessTab />;
    case "user-management":
      return <UserManagementTab />;
    case "rag":
      return <RagTab />;
    case "session-tickets":
      return <SessionTicketsTab />;
    case "line-binding":
      return <LineBindingTab />;
    default:
      return null;
  }
}

export const TabButton = memo(function TabButton({ current, value, onChange }: { current: Tab; value: Tab; onChange: (v: Tab) => void }) {
  return <button className={`tab ${current === value ? "active" : ""}`} onClick={() => onChange(value)}>{value}</button>;
});
