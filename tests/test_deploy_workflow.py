from pathlib import Path


WORKFLOW = Path(".github/workflows/deploy.yml")


def test_deploy_workflow_is_gated_by_successful_main_ci() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_run:" in content
    assert "workflows: [CI]" in content or 'workflows: ["CI"]' in content
    assert "types: [completed]" in content
    assert "github.event.workflow_run.conclusion == 'success'" in content
    assert "github.event.workflow_run.head_branch == 'main'" in content
    assert "github.event.workflow_run.event == 'push'" in content
    assert "github.event.workflow_run.head_sha" in content


def test_deploy_workflow_uses_zeabur_backend_service_and_smoke_check() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "ZEABUR_TOKEN" in content
    assert "vars.ZEABUR_PROJECT_ID" in content
    assert "vars.ZEABUR_SERVICE_ID" in content
    assert "vars.ZEABUR_ENVIRONMENT_ID" in content
    assert "vars.BACKEND_HEALTH_URL" in content
    assert "6a1e814b8fd5d6b81d7ad706" not in content
    assert "6a1e8248d8f8814aa285d8a6" not in content
    assert "6a1e814bb0fc054c4cc406d0" not in content
    assert "deployment list" in content
    assert "commitSHA" in content
    assert "RUNNING" in content
    assert "zeabur" in content
    assert 'curl -fsS "$BACKEND_HEALTH_URL"' in content
