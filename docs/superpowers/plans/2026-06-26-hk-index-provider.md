# HK Index Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an AkShare-based Hong Kong index provider so HK market review does not depend on Yahoo as the primary source.

**Architecture:** Add one focused provider class in the existing market provider module, update symbol normalization and default HK provider order, and extend provider health probes. Keep LongPort/Futu out of scope for this MVP.

**Tech Stack:** Python, pytest, FastAPI service modules, AkShare.

---

### Task 1: Tests

- [ ] Add tests for `^HSI` / `^HSTECH` normalization as HK symbols.
- [ ] Add tests for `AkShareHKIndexProvider` mapping daily AkShare rows into normalized points.
- [ ] Add tests for HK auto routing preferring `akshare_hk_index`.
- [ ] Add tests for provider health HK coverage through `akshare_hk_index`.

### Task 2: Implementation

- [ ] Add HK index normalization in `app/tools/market_symbols.py`.
- [ ] Add `AkShareHKIndexProvider` in `app/tools/market_providers.py`.
- [ ] Register provider and default HK order in `app/tools/market_data.py`.
- [ ] Add `akshare_hk_index` to `/health/providers` probes.
- [ ] Update env examples, Render config, and README.

### Task 3: Verification

- [ ] Run targeted tests.
- [ ] Run full backend tests.
- [ ] Run frontend stock tests and build.
- [ ] Commit and push `main`.

