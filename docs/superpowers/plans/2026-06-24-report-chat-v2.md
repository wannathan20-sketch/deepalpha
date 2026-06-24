# Report Chat V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade report chat with user-scoped persistence, six-turn context, verified section citations, deterministic freshness routing, and optional web evidence.

**Architecture:** Keep SQLite persistence, Markdown section parsing, deterministic routing, and answer orchestration in focused services. The API resolves trusted task context and user identity; the frontend restores history, selects search mode, and links verified citations to stable report section IDs.

**Tech Stack:** FastAPI, Pydantic, SQLite, existing search/LLM clients, React/Vite, pytest.

---

### Task 1: Persistence

**Files:** `app/memory/store.py`, `app/services/report_chat_store.py`, `tests/test_report_chat_store.py`

- [x] Write failing tests for user/task isolation, atomic turn writes, six-turn retrieval, history deletion, and no half-turn on failure.
- [x] Run the tests and confirm missing store behavior.
- [x] Add session/message tables and a focused store API.
- [x] Run the tests until green.

### Task 2: Routing and sections

**Files:** `app/services/report_chat_routing.py`, `app/services/report_sections.py`, `tests/test_report_chat_routing.py`, `tests/test_report_sections.py`

- [x] Write failing tests for temporal intent, search-mode overrides, stable section IDs, and excerpt/URL validation.
- [x] Run the tests and confirm missing modules.
- [x] Implement pure deterministic routing and Markdown section parsing/validation.
- [x] Run the tests until green.

### Task 3: Orchestration and API

**Files:** `app/services/report_chat.py`, `app/schemas.py`, `app/main.py`, `tests/test_report_chat.py`

- [x] Add failing tests for six-turn prompt context, automatic web search, forced modes, search failure degradation, extended response fields, history APIs, user isolation, and stateless Markdown compatibility.
- [x] Run tests and confirm contract failures.
- [x] Extend schemas, orchestrate search and citations, persist only successful task-based turns, and add GET/DELETE history routes.
- [x] Run report-chat tests until green.

### Task 4: Frontend

**Files:** `frontend/src/App.jsx`, `frontend/src/styles.css`

- [x] Add stable report section IDs and temporary highlight behavior.
- [x] Restore task chat history, add search-mode selection and clear-history action.
- [x] Render route, freshness, report citations, and web citations with distinct states.
- [x] Run the frontend production build.

### Task 5: Documentation and verification

**Files:** `README.md`

- [x] Document persistence, six-turn context, search modes, history APIs, and automatic freshness search.
- [x] Run all backend tests.
- [x] Run frontend tests and production build.
- [x] Run Python compilation and `git diff --check`.
- [ ] Review requirements, commit only scoped files, and push after explicit remote confirmation if required.
