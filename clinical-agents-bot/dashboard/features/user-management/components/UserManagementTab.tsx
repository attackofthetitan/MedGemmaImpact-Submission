"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { USER_ROLE_OPTIONS } from "@/lib/model-options";
import type { User, UserCreatePayload, UserUpdatePayload } from "@/lib/types";
import { Button, Card, Input, Select } from "@/components/ui/primitives";
import { ReqLabel } from "@/components/dashboard/common/FormLabels";
import { useDashboardContext } from "@/components/dashboard/shell/DashboardContext";

export function UserManagementTab() {
  const { token, show } = useDashboardContext();
  const [users, setUsers] = useState<User[]>([]);
  const [registerForm, setRegisterForm] = useState<UserCreatePayload>({
    username: "",
    password: "",
    role: "staff",
    name: "",
  });
  const [editRows, setEditRows] = useState<Record<string, UserUpdatePayload>>({});

  const load = useCallback(async () => {
    try {
      const res = await api.listUsers(token);
      const next: Record<string, UserUpdatePayload> = {};
      for (const u of res.users) {
        next[u.username] = {
          username: u.username,
          name: u.name,
          role: u.role,
          active: Boolean(u.active),
        };
      }
      setUsers(res.users);
      setEditRows(next);
    } catch (e) {
      show("error", String(e));
    }
  }, [show, token]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="col">
      <Card title="Register User (Admin)">
        <p className="section-intro">Create a new dashboard user account.</p>
        <div className="form-grid">
          <ReqLabel text="username" htmlFor="register-username" />
          <Input
            id="register-username"
            required
            name="username"
            placeholder="Enter username..."
            value={registerForm.username}
            onChange={(e) => setRegisterForm((v) => ({ ...v, username: e.target.value }))}
          />
          <ReqLabel text="password" htmlFor="register-password" />
          <Input
            id="register-password"
            required
            name="password"
            type="password"
            placeholder="Enter password..."
            value={registerForm.password}
            onChange={(e) => setRegisterForm((v) => ({ ...v, password: e.target.value }))}
          />
          <ReqLabel text="name" htmlFor="register-name" />
          <Input
            id="register-name"
            required
            name="name"
            placeholder="Enter full name..."
            value={registerForm.name}
            onChange={(e) => setRegisterForm((v) => ({ ...v, name: e.target.value }))}
          />
          <ReqLabel text="role" />
          <Select
            required
            value={registerForm.role}
            onChange={(e) => setRegisterForm((v) => ({ ...v, role: e.target.value as UserCreatePayload["role"] }))}
          >
            {USER_ROLE_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
          </Select>
          <Button
            onClick={() =>
              api.registerUser(token, registerForm)
                .then(() => {
                  show("success", "User registered");
                  setRegisterForm({ username: "", password: "", role: "staff", name: "" });
                  load();
                })
                .catch((e) => show("error", String(e)))
            }
          >
            Register
          </Button>
        </div>
      </Card>

      <Card title="Manage Users">
        <p className="section-intro">Update role, name, and active status for existing users.</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>User ID</th>
                <th>LINE Account ID</th>
                <th>Username</th>
                <th>Role</th>
                <th>Name</th>
                <th>Active</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const row = editRows[u.username] ?? {
                  username: u.username,
                  name: u.name,
                  role: u.role,
                  active: Boolean(u.active),
                };
                return (
                  <tr key={u.id}>
                    <td>{u.id}</td>
                    <td>{u.platform_id ?? "-"}</td>
                    <td>{u.username}</td>
                    <td>
                      <Select
                        value={row.role}
                        onChange={(e) =>
                          setEditRows((v) => ({
                            ...v,
                            [u.username]: { ...row, role: e.target.value as UserUpdatePayload["role"] },
                          }))
                        }
                      >
                        {USER_ROLE_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
                      </Select>
                    </td>
                    <td>
                      <Input
                        placeholder={`edit-name-${u.username}`}
                        value={row.name ?? ""}
                        onChange={(e) =>
                          setEditRows((v) => ({
                            ...v,
                            [u.username]: { ...row, name: e.target.value },
                          }))
                        }
                      />
                    </td>
                    <td>
                      <label className="small">
                        <input
                          type="checkbox"
                          checked={Boolean(row.active)}
                          onChange={(e) =>
                            setEditRows((v) => ({
                              ...v,
                              [u.username]: { ...row, active: e.target.checked },
                            }))
                          }
                        />
                      </label>
                    </td>
                    <td>{u.created_at ?? "-"}</td>
                    <td>
                      <Button
                        variant="secondary"
                        onClick={() =>
                          api.updateUser(token, row)
                            .then(() => {
                              show("success", `Updated ${u.username}`);
                              load();
                            })
                            .catch((e) => show("error", String(e)))
                        }
                      >
                        Save
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

