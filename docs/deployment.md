# Deployment

## Architecture

- **Frontend** — Vite/React app built by GitHub Actions, deployed to GitHub Pages on every push to `main`
- **Backend** — FastAPI + PostGIS, not yet hosted (runs locally via `docker compose up`)

## Local dev

```bash
docker compose up          # postgres + postgis on :5432
uvicorn api.main:app --reload  # api on :8000
cd app/map_ui && npm run dev   # frontend on :5173
```

Copy `.env.example` to `.env` and fill in your API keys.

## GitHub Pages

Deploys automatically via `.github/workflows/deploy-pages.yml` on push to `main`.
Set `VITE_API_BASE_URL` as a GitHub repo variable to point the frontend at a live backend:

```bash
gh variable set VITE_API_BASE_URL --body "https://your-api-url"
git commit --allow-empty -m "trigger rebuild" && git push
```

## Fly.io (ready, needs card)

Config is written (`Dockerfile`, `.dockerignore`, `fly.toml`). Requires a credit card on file even for the free allowance.

When ready:

```bash
fly apps create open-supply-chain-api
fly postgres create --name open-supply-chain-db --region iad
fly postgres attach open-supply-chain-db --app open-supply-chain-api
fly secrets set ANTHROPIC_API_KEY=... OPENAI_API_KEY=...
fly deploy
fly postgres connect -a open-supply-chain-db < db/schema.sql
gh variable set VITE_API_BASE_URL --body "https://open-supply-chain-api.fly.dev"
```

## Render + Supabase (free, no card)

Alternative if Fly.io is undesirable. Tradeoff: Render free tier cold-starts after 15 min idle (~30s wake).

- Supabase: managed Postgres with PostGIS, free forever
- Render: FastAPI web service, free tier, deploy via `render.yaml`

Not yet configured.
