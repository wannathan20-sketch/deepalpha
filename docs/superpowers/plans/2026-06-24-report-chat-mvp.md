# Report Chat MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reliable single-report follow-up Q&A through `POST /chat/report`, with strategy focus, structured answers, a simple report-page chat history, tests, and documentation.

**Architecture:** A focused `app/services/report_chat.py` service builds bounded context from a completed task or submitted Markdown, calls the existing LLM once, validates JSON, and filters citations against report-owned URLs. FastAPI owns request validation and task lookup; React owns ephemeral history for the currently displayed report.

**Tech Stack:** FastAPI, Pydantic, existing OpenAI-compatible LLM client, SQLite-backed report tasks, React 18, Vite, pytest.

---

### Task 1: Define and test the report-chat contract

**Files:**
- Modify: `app/schemas.py`
- Create: `tests/test_report_chat.py`

- [x] Add failing API tests for successful task-based Q&A, direct Markdown Q&A, missing context, missing/unfinished task, invalid strategy, strategy prompt focus, citation filtering, and `LLMProviderError` → HTTP 503.
- [x] Run `pytest tests/test_report_chat.py -q` and confirm failures are caused by the missing route/service.
- [x] Add `ReportChatRequest`, `ReportChatResponse`, and cited-source models with trimmed non-empty text validation and the five strategy literals.

### Task 2: Implement bounded report Q&A

**Files:**
- Create: `app/services/report_chat.py`
- Modify: `app/main.py`

- [x] Implement context construction from task result or direct Markdown.
- [x] Limit report/profile/source context size and build strategy-specific prompts.
- [x] Call `generate_text`, parse a JSON object, validate required fields, and convert malformed model output to `LLMProviderError`.
- [x] Extract allowed report/source-quality URLs and remove model citations not present in that allowlist.
- [x] Add `POST /chat/report`, reuse report access validation, and return 404/400 for invalid task context.
- [x] Run `pytest tests/test_report_chat.py -q` until green.

### Task 3: Preserve structured profiles in report task results

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_api.py`

- [x] Add a failing assertion that report responses/tasks retain `market_profile` and `financial_profile`.
- [x] Extend `_build_report_response` without removing existing fields.
- [x] Run targeted API tests and confirm green.

### Task 4: Add the report-page follow-up UI

**Files:**
- Modify: `frontend/src/App.jsx`

- [x] Add question, strategy, history, loading, and error state.
- [x] Clear chat state when a new report starts.
- [x] Submit the current successful `task_id`, falling back to `markdown_report`.
- [x] Render a compact input, strategy selector, loading/error feedback, and response history with key points, risks, citations, and data warning.
- [x] Run `npm run build` in `frontend`.

### Task 5: Document and verify

**Files:**
- Modify: `README.md`

- [x] Document route, request modes, strategies, response fields, and production 503 behavior.
- [x] Run `pytest -q`.
- [x] Run `npm run test:stock` and `npm run build` in `frontend`.
- [x] Run `git diff --check` and inspect the final diff against every requirement.
- [ ] Commit all implementation changes and push the current branch to GitHub.
