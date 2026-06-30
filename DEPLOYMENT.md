# Deploying Aegis-MCP on Render

Render supports multiple web services in one account on the free tier, which makes it a straightforward choice for running the FastAPI API and Next.js console as separate services.

## Prerequisites

- A [Render](https://render.com) account
- This repository pushed to GitHub
- An upstream MCP server URL (or a placeholder for demo)

## Service 1: FastAPI API

1. **New → Web Service** → connect your `aegis-mcp` repo.
2. **Name:** `aegis-mcp-api`
3. **Root Directory:** leave blank (repo root)
4. **Runtime:** Docker
5. **Dockerfile Path:** `./Dockerfile`
6. **Instance type:** Free (or paid for always-on)

### Environment variables (Render dashboard)

| Variable | Required | Example |
|----------|----------|---------|
| `UPSTREAM_MCP_URL` | Yes | `https://your-upstream.example.com/mcp` |
| `ANTHROPIC_API_KEY` | If `semantic_judge: anthropic` | `sk-ant-...` |
| `HITL_WEBHOOK_URL` | No | `https://hooks.slack.com/...` |
| `HITL_REVIEW_BASE_URL` | No | `https://aegis-mcp-api.onrender.com` |

7. Deploy. Note the public URL, e.g. `https://aegis-mcp-api.onrender.com`.

## Service 2: Next.js Console

1. **New → Web Service** → same repo.
2. **Name:** `aegis-mcp-console`
3. **Root Directory:** `console`
4. **Runtime:** Docker
5. **Dockerfile Path:** `./console/Dockerfile` (relative to repo root — set **Root Directory** to `console` and Dockerfile to `Dockerfile`)

### Build arguments / environment

| Variable | Required | Value |
|----------|----------|-------|
| `NEXT_PUBLIC_API_URL` | Yes | `https://aegis-mcp-api.onrender.com` |

Set `NEXT_PUBLIC_API_URL` as an **environment variable** at build time on Render (Docker build arg is wired in the Dockerfile via `ARG NEXT_PUBLIC_API_URL`).

6. Deploy. Console URL: `https://aegis-mcp-console.onrender.com`.

## Local parity with Docker Compose

```bash
cp .env.example .env
# edit .env
docker compose up --build
```

- API: http://localhost:8000
- Console: http://localhost:3000

## Health checks

- API: `GET https://aegis-mcp-api.onrender.com/v1/pending` should return `[]` or a JSON list.
- Console: open the URL; cards appear when escalated calls exist.

## Notes

- Free-tier Render services spin down after inactivity; first request may be slow.
- Do not commit `.env` or real API keys. Policy config stays in `aegis-config.yaml` (non-secret).
- For stdio upstream MCP servers, run the upstream on the same host/network and point `UPSTREAM_MCP_URL` at its HTTP adapter if one exists; raw stdio is not exposed over Render's HTTP model.

## Railway alternative

Railway follows the same pattern: two services from the same repo, one using the root `Dockerfile`, one using `console/Dockerfile`, with `NEXT_PUBLIC_API_URL` pointing at the API service's public URL.
