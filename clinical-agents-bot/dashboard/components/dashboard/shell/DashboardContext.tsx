"use client";

import { createContext, useContext } from "react";
import { getPermissions } from "@/lib/permissions";
import type { User } from "@/lib/types";
import type { ShowToast } from "@/components/dashboard/shell/useToast";

export type DashboardContextValue = {
  token: string;
  user: User;
  perms: ReturnType<typeof getPermissions>;
  show: ShowToast;
  refreshUser: (user: User) => void;
};

export const DashboardContext = createContext<DashboardContextValue | null>(null);

export function useDashboardContext(): DashboardContextValue {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error("useDashboardContext must be used inside DashboardContext provider");
  return ctx;
}
