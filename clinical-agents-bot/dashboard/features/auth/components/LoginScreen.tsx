"use client";

import type React from "react";
import { Button, Card, Input } from "@/components/ui/primitives";
import { ReqLabel } from "@/components/dashboard/common/FormLabels";

export function LoginScreen({
  login,
  setLogin,
  onLogin,
}: {
  login: { username: string; password: string };
  setLogin: React.Dispatch<React.SetStateAction<{ username: string; password: string }>>;
  onLogin: (e: React.FormEvent) => void | Promise<void>;
}) {
  return (
    <main id="main-content">
      <Card title="Dashboard Login">
        <form className="col" onSubmit={onLogin} method="post">
          <ReqLabel text="Username" htmlFor="login-username" />
          <Input id="login-username" required autoComplete="username" placeholder="Enter username..." value={login.username} onChange={(e) => setLogin((v) => ({ ...v, username: e.target.value }))} />
          <ReqLabel text="Password" htmlFor="login-password" />
          <Input id="login-password" required autoComplete="current-password" placeholder="Enter password..." type="password" value={login.password} onChange={(e) => setLogin((v) => ({ ...v, password: e.target.value }))} />
          <Button type="submit">Sign in</Button>
        </form>
      </Card>
    </main>
  );
}
