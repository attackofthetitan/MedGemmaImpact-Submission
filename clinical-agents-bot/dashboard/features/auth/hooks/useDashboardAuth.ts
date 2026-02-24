"use client";

import type React from "react";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";
import type { ShowToast } from "@/components/dashboard/shell/useToast";

export function useDashboardAuth(show: ShowToast) {
  const [token, setToken] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return localStorage.getItem("dashboard-token") ?? "";
  });
  const [user, setUser] = useState<User | null>(null);
  const [login, setLogin] = useState({ username: "", password: "" });

  useEffect(() => {
    if (!token) return;
    api.me(token)
      .then(setUser)
      .catch(() => {
        setToken("");
        setUser(null);
        localStorage.removeItem("dashboard-token");
      });
  }, [token]);

  const onLogin = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await api.login(login.username, login.password);
      setToken(res.access_token);
      setUser(res.user);
      localStorage.setItem("dashboard-token", res.access_token);
    } catch (err) {
      show("error", `Login failed: ${String(err)}`);
    }
  }, [login.password, login.username, show]);

  const logout = useCallback(() => {
    localStorage.removeItem("dashboard-token");
    setToken("");
    setUser(null);
  }, []);

  return {
    token,
    user,
    login,
    setLogin,
    onLogin,
    logout,
    refreshUser: setUser,
  };
}
