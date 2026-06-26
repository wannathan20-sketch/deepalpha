# Production Reliability Iteration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add CI-gated Zeabur deployment, richer market review visibility, and sanitized provider health monitoring.

**Architecture:** Keep changes incremental around existing FastAPI endpoints and the existing market-data abstraction. Add a focused provider health service, a small API route, one GitHub Actions workflow, and simple frontend labels without introducing stale cache or new agent routing.

**Tech Stack:** FastAPI, pytest, GitHub Actions, Zeabur CLI via `npx zeabur`, React/Vite.

---

### Task 1: Provider health service and endpoint

**Files:**
- Create: `app/services/provider_health.py`
- Modify: `app/main.py`
- Test: `tests/test_provider_health.py`
- Test: `tests/test_api.py`

- [ ] Write failing tests for healthy/degraded provider aggregation and sanitized failure reasons.
- [ ] Implement `build_provider_health()` with concurrent probes through `get_market_chart`.
- [ ] Add `GET /health/providers` with `PROVIDER_HEALTH_CACHE_TTL_SECONDS`.
- [ ] Run targeted provider health and API tests.

### Task 2: Market review observability labels

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `app/config.py`
- Modify: `.env.example`
- Modify: `.env.zeabur.example`
- Modify: `render.yaml`
- Test: existing frontend build/test and backend config/API tests.

- [ ] Add runtime config fields for market review and provider health TTLs.
- [ ] Show `cache_hit`, `generated_at`, `provider`, `source_url`, direct index vs ETF proxy, and all summary lines in `MarketReviewPanel`.
- [ ] Document env defaults in examples/deploy config.
- [ ] Run frontend tests and build.

### Task 3: CI-gated Zeabur deploy workflow

**Files:**
- Create: `.github/workflows/deploy.yml`
- Test: `tests/test_deploy_workflow.py`
- Modify: `README.md`

- [ ] Write failing workflow structure tests.
- [ ] Add workflow triggered by successful `CI` workflow_run on `main`.
- [ ] Checkout the tested SHA, authenticate Zeabur with `ZEABUR_TOKEN`, deploy backend service, poll latest deployment to `RUNNING`, and smoke-check `/health`.
- [ ] Document GitHub Secret setup and disabling Zeabur native auto deploy.

### Task 4: Full verification and release

**Files:**
- Commit all touched files.

- [ ] Run backend test suite.
- [ ] Run frontend stock tests.
- [ ] Run frontend production build.
- [ ] Commit and push `main`.
- [ ] Check remote CI; if green, the new deploy workflow will deploy subsequent successful `main` runs once `ZEABUR_TOKEN` is configured.

