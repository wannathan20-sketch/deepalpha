from pathlib import Path


ROOT = Path(".")
README = ROOT / "README.md"
DEV_SCRIPT = ROOT / "scripts" / "dev.sh"
COMPOSE_FILE = ROOT / "docker-compose.yml"


def test_one_command_dev_script_documents_and_starts_both_apps() -> None:
    content = DEV_SCRIPT.read_text(encoding="utf-8")

    assert content.startswith("#!/usr/bin/env bash")
    assert "uvicorn app.main:app --reload --host 127.0.0.1 --port ${BACKEND_PORT:-8000}" in content
    assert "npm install" in content
    assert "npm run dev -- --host 127.0.0.1 --port ${FRONTEND_PORT:-5173}" in content
    assert "trap cleanup EXIT INT TERM" in content


def test_docker_compose_runs_backend_and_frontend_demo() -> None:
    content = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "deepalpha-api" in content
    assert "deepalpha-web" in content
    assert "APP_ENV=development" in content
    assert "LLM_PROVIDER=mock" in content
    assert "SEARCH_PROVIDER=mock" in content
    assert "VITE_API_BASE=http://localhost:8000" in content
    assert '"8000:8000"' in content
    assert '"5173:5173"' in content


def test_readme_links_quick_start_and_project_showcase_screenshot() -> None:
    content = README.read_text(encoding="utf-8")

    assert "bash scripts/dev.sh" in content
    assert "docker compose up --build" in content
    assert "## 项目展示" in content
    assert "docs/images/deepalpha-showcase.png" in content
    assert "docs/images/deepalpha-market-review.png" not in content
    assert "docs/images/deepalpha-workbench.png" not in content
    assert "docs/images/deepalpha-report.png" not in content
