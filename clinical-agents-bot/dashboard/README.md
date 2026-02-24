# Clinical Agents Dashboard

Admin/operator dashboard for `clinical-agents-bot` and `clinical-agents` workflows.

## Quick Start (Real Backend)

```bash
cd clinical-agents-bot/dashboard
npm install
NEXT_PUBLIC_AGENT_BASE_URL=http://localhost:8888/dashboard npm run dev:real
```

Open:
- `http://localhost:3000/dashboard`

Expected frontend request shape:
- `/api/v1/...`
- resolved via base URL to `/dashboard/api/v1/...`

## Build

```bash
NEXT_PUBLIC_AGENT_BASE_URL=http://localhost:8888/dashboard npm run build:prod
```

Serve static output if needed:

```bash
npm run serve:static
```

## Environment Variables

| Variable | Purpose | Typical Value |
|---|---|---|
| `NEXT_PUBLIC_AGENT_BASE_URL` | Base URL for dashboard API routing | `http://localhost:8888/dashboard` |

## Tabs

- `overview`
- `ehr-create`
- `user-access` (admin/physician)
- `user-management` (admin only)
- `rag` (admin/physician)
- `session-tickets`
- `line-binding`

## Notes

- The dashboard frontend is configured for real API mode only.
