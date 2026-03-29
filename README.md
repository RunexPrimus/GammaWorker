# Presenton Worker Service

This package is for a Koyeb Worker or any long-running background process.
It does not expose incoming endpoints. Instead, it polls the web service for queued jobs.

## Deploy
Use as a Koyeb Worker.

Start command:

```bash
python -m app.runner
```

## Important envs
- `WEB_INTERNAL_BASE_URL`
- `INTERNAL_API_TOKEN`
- `BOT_TOKEN`
- `PRESENTON_BASE_URL`

`PRESENTON_BASE_URL` should point to your self-hosted Presenton, not the cloud API, if you want local processing.
