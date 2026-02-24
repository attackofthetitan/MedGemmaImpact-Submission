# Clinical-Agent Bot

LINE bot service for the clinical-agent workflow. This README is for `clinical-agents-bot` only (not dashboard frontend docs).

## Purpose

- Receive LINE webhook events.
- Route patient/staff messages into clinical-agent backend workflows.
- Handle review-to-send lifecycle.
- Provide bot-related API routes used by operators.

## Required Environment Variables

Set these before starting the bot:

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `ADMIN_PASSWORD`

Optional:

- `ADMIN_USERNAME` (default: `admin`)
- `AGENT_URL` (default: `http://localhost:8080/`)

Example:

```bash
export LINE_CHANNEL_SECRET="<your-line-channel-secret>"
export LINE_CHANNEL_ACCESS_TOKEN="<your-line-channel-access-token>"
export ADMIN_PASSWORD="<your-admin-password>"
export ADMIN_USERNAME="admin"
export AGENT_URL="http://localhost:8080/"
```

Notes:

- LINE channel secret/access token are loaded from env in `config.py`.
- Admin auth password is loaded from env via `ADMIN_PASSWORD`.

## Run

```bash
cd clinical-agents-bot
uvicorn chatbot:app --host 0.0.0.0 --port 8888
```

## Core Endpoints

- `POST /callback`  
  LINE webhook entrypoint (`X-Line-Signature` required).

- `POST /dashboard/api/v1/api/line/send?patient_id=...&session_id=...`  
  Trigger final send to LINE after review.

- `POST /dashboard/api/v1/line-binding/code`
- `GET /dashboard/api/v1/line-binding/code/{binding_id}`
- `POST /dashboard/api/v1/line-binding/code/{binding_id}/cancel`

## High-Level Flow

1. Patient sends LINE message to bot.
2. Bot resolves patient/staff context and forwards to clinical-agent backend.
3. Staff review response updates session state (`needs_revision`, `ready_to_send`, `escalated`).
4. Approved response is sent to patient through LINE push/send flow.