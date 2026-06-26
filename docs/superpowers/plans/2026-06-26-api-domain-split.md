# API Domain Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make DeepAlpha use `api.deepalpha.best` as the production backend API while keeping local development simple.

**Architecture:** Extract frontend API base resolution into a tiny tested module, update `App.jsx` to consume it, update environment examples and README, then verify and deploy through the existing CI-gated Zeabur workflow.

**Tech Stack:** Vite, React, Node test runner, FastAPI CORS env config, GitHub Actions.

---

### Task 1: Frontend API base resolver

- [ ] Add failing tests in `frontend/src/apiClient.test.mjs`.
- [ ] Add `frontend/src/apiClient.js` with `resolveApiBase` and `API_BASE`.
- [ ] Import `API_BASE` in `frontend/src/App.jsx`.
- [ ] Update frontend test script so CI runs all `.test.mjs` files.

### Task 2: Config and docs

- [ ] Set Zeabur env example CORS to `https://(www\.)?deepalpha\.best`.
- [ ] Add frontend env example for `VITE_API_BASE=https://api.deepalpha.best`.
- [ ] Document DNS/Zeabur binding for `api.deepalpha.best`.

### Task 3: Verification and deploy

- [ ] Run backend tests.
- [ ] Run frontend tests and build.
- [ ] Commit and push `main`.
- [ ] Confirm CI and deploy workflow complete.

