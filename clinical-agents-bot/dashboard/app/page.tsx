"use client";

import { useMemo, useState } from "react";
import { getPermissions } from "@/lib/permissions";
import { Button, Card } from "@/components/ui/primitives";
import { DashboardContext, type DashboardContextValue } from "@/components/dashboard/shell/DashboardContext";
import { DashboardTabPanel, TabButton, type Tab } from "@/components/dashboard/shell/DashboardTabs";
import { useToast } from "@/components/dashboard/shell/useToast";
import { LoginScreen } from "@/features/auth/components/LoginScreen";
import { useDashboardAuth } from "@/features/auth/hooks/useDashboardAuth";

export default function DashboardPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const { message, show } = useToast();
  const { token, user, login, setLogin, onLogin, logout, refreshUser } = useDashboardAuth(show);

  const perms = useMemo(() => (user ? getPermissions(user.role) : null), [user]);
  const visibleTabs = useMemo<Tab[]>(() => {
    if (!user) return [];
    const isAdmin = user.role === "admin";
    const isPhysician = user.role === "physician";
    return [
      "overview",
      "ehr-create",
      ...(isAdmin || isPhysician ? ["user-access"] as Tab[] : []),
      ...(isAdmin ? ["user-management"] as Tab[] : []),
      ...(isAdmin || isPhysician ? ["rag"] as Tab[] : []),
      "session-tickets",
      "line-binding",
    ];
  }, [user]);

  const contextValue = useMemo<DashboardContextValue | null>(() => {
    if (!user || !perms) return null;
    return {
      token,
      user,
      perms,
      show,
      refreshUser,
    };
  }, [perms, refreshUser, show, token, user]);

  if (!user) {
    return <LoginScreen login={login} setLogin={setLogin} onLogin={onLogin} />;
  }

  return (
    <main id="main-content" className="col">
      <Card>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h1>Dashboard</h1>
            <p className="small">{user.name} ({user.role}) · {user.username}</p>
          </div>
          <Button variant="secondary" onClick={logout}>Logout</Button>
        </div>
      </Card>

      <div className="tabbar">
        {visibleTabs.map((value) => (
          <TabButton key={value} current={tab} value={value} onChange={setTab} />
        ))}
      </div>

      {message ? <div aria-live="polite" className={message.type === "success" ? "success" : "error"}>{message.text}</div> : null}

      <DashboardContext.Provider value={contextValue!}>
        <DashboardTabPanel tab={tab} visibleTabs={visibleTabs} />
      </DashboardContext.Provider>
    </main>
  );
}
