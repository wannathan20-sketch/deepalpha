# API Domain Split Design

## Goal

Separate the public frontend domain from the backend API domain:

- Frontend: `https://deepalpha.best`
- Backend API: `https://api.deepalpha.best`

This avoids the current ambiguity where `https://deepalpha.best/health` is handled by the frontend SPA instead of the FastAPI backend.

## Design

Frontend API base resolution becomes environment-aware:

1. If `VITE_API_BASE` is set, use it.
2. If the browser hostname is `deepalpha.best` or `www.deepalpha.best`, default to `https://api.deepalpha.best`.
3. Otherwise, default local development to `http://127.0.0.1:8000`.

Backend CORS examples allow the frontend domain by default in Zeabur production config:

```text
https://(www\.)?deepalpha\.best
```

The code change does not bind DNS by itself. Zeabur and domain DNS still need `api.deepalpha.best` to point at the backend service. README documents the exact expected setup.

## Testing

Add frontend unit tests for API base resolution:

- explicit env var wins;
- `deepalpha.best` maps to `https://api.deepalpha.best`;
- `www.deepalpha.best` maps to `https://api.deepalpha.best`;
- localhost maps to `http://127.0.0.1:8000`.

Keep backend and frontend build verification unchanged.

