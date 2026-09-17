"""
Adversarial Empirical Stress Tests for Remote Trigger API & GitHub Actions Workflow.
Targets:
- src/nfl_odds/dashboard/api.py (/api/trigger-workflow, /api/workflow-status, /api/run-pipeline)
- .github/workflows/update_odds.yml (YAML syntax, schema, security posture)
"""
import os
import yaml
import httpx
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from nfl_odds.dashboard.api import app, get_github_repo_info, get_github_branch
from nfl_odds.dashboard.auth import create_admin_token


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_headers():
    token = create_admin_token()
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# Category 1: Authentication & Authorization Stress Tests
# ============================================================================

def test_adv_trigger_workflow_unauthenticated_header_returns_403(client):
    """Stress test: Missing Authorization header completely rejected with 403."""
    res = client.post("/api/trigger-workflow", json={"week": 2, "fast": False})
    assert res.status_code == 403
    assert "Administrador" in res.json()["detail"]


@pytest.mark.parametrize(
    "bad_auth_header",
    [
        "Bearer",
        "Bearer ",
        "Bearer invalid_garbage_token",
        "Bearer 12345:abcdef",
        "Basic dXNlcjpwYXNz",
        "Token some_random_token",
        "null",
        "",
    ],
)
def test_adv_trigger_workflow_malformed_auth_header_returns_403(client, bad_auth_header):
    """Stress test: Malformed, spoofed, or invalid Authorization headers rejected with 403."""
    headers = {"Authorization": bad_auth_header} if bad_auth_header else {}
    res = client.post("/api/trigger-workflow", headers=headers, json={"week": 2})
    assert res.status_code == 403
    assert "Administrador" in res.json()["detail"]


def test_adv_trigger_workflow_tampered_cookie_returns_403(client):
    """Stress test: Tampered cookie rejected with 403."""
    client.cookies.set("nfl_admin_token", "tampered_signature_fake_jwt")
    res = client.post("/api/trigger-workflow", json={"week": 2})
    assert res.status_code == 403


def test_adv_trigger_workflow_valid_cookie_accepted_as_admin(client, monkeypatch):
    """Stress test: Valid nfl_admin_token cookie provides authenticated admin access."""
    valid_token = create_admin_token()
    client.cookies.set("nfl_admin_token", valid_token)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_PAT", raising=False)
    monkeypatch.delenv("GITHUB_PAT", raising=False)

    # Reaches token validation (400) because admin auth succeeds
    res = client.post("/api/trigger-workflow", json={"week": 2})
    assert res.status_code == 400
    assert "GITHUB_TOKEN não configurado" in res.json()["detail"]


def test_adv_run_pipeline_unauthenticated_returns_403(client):
    """Stress test: POST /api/run-pipeline rejected with 403 when unauthenticated."""
    res = client.post("/api/run-pipeline")
    assert res.status_code == 403
    assert "Administrador" in res.json()["detail"]


# ============================================================================
# Category 2: Missing Token Clean Error Handling (Never 500)
# ============================================================================

@pytest.mark.parametrize(
    "token_value",
    [
        None,
        "",
        "   ",
        "\t\n  \r",
    ],
)
def test_adv_trigger_workflow_missing_or_blank_token_returns_400(client, admin_headers, monkeypatch, token_value):
    """Stress test: Missing, empty, or whitespace-only token cleanly returns 400 (never 500)."""
    if token_value is None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_PAT", raising=False)
        monkeypatch.delenv("GITHUB_PAT", raising=False)
    else:
        monkeypatch.setenv("GITHUB_TOKEN", token_value)
        monkeypatch.delenv("GH_PAT", raising=False)
        monkeypatch.delenv("GITHUB_PAT", raising=False)

    res = client.post("/api/trigger-workflow", headers=admin_headers, json={"week": 2})
    assert res.status_code == 400
    assert "GITHUB_TOKEN não configurado" in res.json()["detail"]
    assert "actions:write" in res.json()["detail"]


def test_adv_run_pipeline_render_without_token_returns_clean_400(client, admin_headers, monkeypatch):
    """Stress test: On Render environment without GITHUB_TOKEN, run-pipeline returns clean 400 with guidance."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_PAT", raising=False)
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    monkeypatch.setenv("RENDER", "true")

    res = client.post("/api/run-pipeline", headers=admin_headers)
    assert res.status_code == 400
    assert "512MB de RAM" in res.json()["detail"]
    assert "Configure a variável GITHUB_TOKEN no Render" in res.json()["detail"]


# ============================================================================
# Category 3: Simulated GitHub Upstream Errors & Network Failures
# ============================================================================

@pytest.mark.parametrize(
    "gh_status,gh_body,expected_status,expected_text",
    [
        (401, '{"message": "Bad credentials"}', 401, "Token do GitHub inválido"),
        (403, '{"message": "Resource not accessible by personal access token"}', 403, "actions:write"),
        (404, '{"message": "Not Found"}', 404, "não encontrado no branch"),
        (422, '{"message": "Workflow does not have workflow_dispatch trigger"}', 422, "Parâmetros de workflow inválidos"),
        (500, '{"message": "Internal Server Error"}', 500, "Erro do GitHub (500)"),
        (502, '<html>502 Bad Gateway</html>', 502, "Erro do GitHub (502)"),
        (503, 'Service Unavailable', 503, "Erro do GitHub (503)"),
        (504, 'Gateway Timeout', 504, "Erro do GitHub (504)"),
        (429, '{"message": "API rate limit exceeded"}', 429, "Erro do GitHub (429)"),
    ],
)
def test_adv_trigger_workflow_upstream_github_status_codes(
    client, admin_headers, monkeypatch, gh_status, gh_body, expected_status, expected_text
):
    """Stress test: Complete spectrum of upstream GitHub HTTP status codes mapped cleanly."""
    monkeypatch.setenv("GITHUB_TOKEN", "mock_secret_token_12345")

    mock_resp = MagicMock()
    mock_resp.status_code = gh_status
    mock_resp.text = gh_body
    if "{" in gh_body:
        mock_resp.json.return_value = {"message": gh_body}
    else:
        mock_resp.json.side_effect = Exception("Not JSON")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = client.post(
            "/api/trigger-workflow",
            headers=admin_headers,
            json={"week": 2, "fast": True},
        )
        assert res.status_code == expected_status
        assert expected_text in res.json()["detail"]
        # Crucial security check: Token must never leak into client detail message
        assert "mock_secret_token_12345" not in res.json()["detail"]


@pytest.mark.parametrize(
    "exception_cls,msg",
    [
        (httpx.ConnectTimeout, "Connection timed out after 15.0s"),
        (httpx.ReadTimeout, "Read timed out waiting for GitHub"),
        (httpx.ConnectError, "Failed to establish new connection: Name or service not known"),
        (httpx.RemoteProtocolError, "Server disconnected unexpectedly"),
        (httpx.PoolTimeout, "Connection pool timeout"),
    ],
)
def test_adv_trigger_workflow_network_and_timeout_failures(client, admin_headers, monkeypatch, exception_cls, msg):
    """Stress test: Simulated low-level network failures and timeouts raise clean 502."""
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = exception_cls(msg)
        res = client.post("/api/trigger-workflow", headers=admin_headers, json={"week": 2})
        assert res.status_code == 502
        assert "Falha de rede ao contatar a API do GitHub Actions" in res.json()["detail"]


def test_adv_trigger_workflow_runs_lookup_failure_still_returns_200(client, admin_headers, monkeypatch):
    """Stress test: If secondary runs lookup times out or fails, dispatch still succeeds and falls back to actions_url."""
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")

    mock_dispatch = MagicMock()
    mock_dispatch.status_code = 204

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.return_value = mock_dispatch
        mock_get.side_effect = httpx.ReadTimeout("Timeout fetching runs")

        res = client.post("/api/trigger-workflow", headers=admin_headers, json={"week": 2})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["run_id"] is None
        assert "actions/workflows/update_odds.yml" in data["run_url"]


def test_adv_trigger_workflow_non_json_422_unhandled_crash_defect(client, admin_headers, monkeypatch):
    """
    Empirical bug verification: When upstream returns 422 with a non-JSON body,
    api.py:1294 calls resp.json() without catching json.decoder.JSONDecodeError,
    causing an unhandled exception instead of a clean HTTPException.
    """
    import json
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")

    mock_resp = MagicMock()
    mock_resp.status_code = 422
    mock_resp.text = "<html>422 Unprocessable Entity - Proxy Error</html>"
    def raise_decode():
        raise json.decoder.JSONDecodeError("Expecting value", "doc", 0)
    mock_resp.json = raise_decode

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(json.decoder.JSONDecodeError):
            client.post("/api/trigger-workflow", headers=admin_headers, json={"week": 2})


# ============================================================================
# Category 4: Input Validation & Boundary Stress Tests
# ============================================================================

def test_adv_trigger_workflow_invalid_week_type_rejected_422(client, admin_headers):
    """Stress test: Passing string or script injection into week rejected by Pydantic (422)."""
    res = client.post(
        "/api/trigger-workflow",
        headers=admin_headers,
        json={"week": "2; rm -rf /", "fast": False},
    )
    assert res.status_code == 422


def test_adv_trigger_workflow_custom_workflow_and_boundaries(client, admin_headers, monkeypatch):
    """Stress test: Valid boundaries (week 18, custom workflow file) correctly forwarded to GitHub payload."""
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")
    monkeypatch.setenv("GITHUB_BRANCH", "staging")

    mock_dispatch = MagicMock()
    mock_dispatch.status_code = 204

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.return_value = mock_dispatch
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"workflow_runs": []})

        res = client.post(
            "/api/trigger-workflow",
            headers=admin_headers,
            json={"week": 18, "fast": True, "workflow_id": "custom_pipeline.yml"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "custom_pipeline.yml" in data["message"]
        assert "Semana 18" in data["message"]

        # Verify dispatched URL and payload
        args, kwargs = mock_post.call_args
        assert "custom_pipeline.yml" in args[0]
        assert kwargs["json"]["inputs"]["week"] == "18"
        assert kwargs["json"]["inputs"]["fast"] == "true"
        assert kwargs["json"]["ref"] == "staging"


# ============================================================================
# Category 5: Workflow Status Endpoint Robustness
# ============================================================================

def test_adv_workflow_status_handles_github_exception_gracefully(client, monkeypatch):
    """Stress test: Upstream failure in workflow-status returns status: 'error' without crashing (HTTP 200)."""
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectTimeout("Status endpoint timeout")
        res = client.get("/api/workflow-status?run_id=99999")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "error"
        assert "Status endpoint timeout" in data["message"]


def test_adv_workflow_status_handles_not_found_cleanly(client, monkeypatch):
    """Stress test: Non-existent run_id mapped to status: not_found."""
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = client.get("/api/workflow-status?run_id=111111111")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "not_found"


# ============================================================================
# Category 6: GitHub Actions Workflow YAML Syntax & Schema Validation
# ============================================================================

def test_adv_workflow_yaml_syntax_and_schema():
    """Stress test: Validates .github/workflows/update_odds.yml syntax, schema, and security settings."""
    workflow_path = ".github/workflows/update_odds.yml"
    assert os.path.exists(workflow_path), f"{workflow_path} must exist"

    with open(workflow_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Parse YAML
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict), "Workflow YAML must parse as a dictionary"

    # 2. Top-level schema
    assert "name" in parsed
    on_block = parsed.get("on") or parsed.get(True)
    assert on_block is not None, "Workflow must contain 'on' trigger specification"
    assert "workflow_dispatch" in on_block
    assert "jobs" in parsed
    assert "scrape-and-predict" in parsed["jobs"]

    # 3. Inputs schema
    inputs = on_block["workflow_dispatch"].get("inputs", {})
    assert "week" in inputs, "workflow_dispatch must define 'week' input"
    assert "fast" in inputs, "workflow_dispatch must define 'fast' input"
    assert inputs["fast"].get("type") == "boolean"

    # 4. Permissions check (Least Privilege + Git Push)
    assert "permissions" in parsed
    permissions = parsed["permissions"]
    assert permissions.get("contents") == "write", "Workflow requires 'contents: write' to push updated parquets"
    assert permissions.get("actions") == "read", "Workflow requires 'actions: read' for concurrency/checks"

    # 5. Concurrency control (Prevent concurrent git push collisions)
    assert "concurrency" in parsed
    concurrency = parsed["concurrency"]
    assert "group" in concurrency
    assert concurrency.get("cancel-in-progress") is False, "Must not cancel in-progress scraping/pipeline runs"

    # 6. Job steps inspection
    job = parsed["jobs"]["scrape-and-predict"]
    assert job.get("runs-on") == "ubuntu-latest"
    assert job.get("timeout-minutes") == 45

    steps = job.get("steps", [])
    step_names = [s.get("name", "") for s in steps]

    assert any("Checkout" in n for n in step_names), "Must checkout repository"
    assert any("uv" in n for n in step_names), "Must install uv"
    assert any("Playwright" in n for n in step_names), "Must install Playwright Chromium"
    assert any("Scraper" in n for n in step_names), "Must run Betclic scraper"
    assert any("Predictive Pipeline" in n for n in step_names), "Must run predictive pipeline"
    assert any("Commit and push" in n for n in step_names), "Must commit and push updated files"

    # 7. Git push safety check in commit step
    commit_step = next(s for s in steps if "Commit and push" in s.get("name", ""))
    commit_script = commit_step.get("run", "")
    assert "[skip ci]" in commit_script, "Git commit message must include [skip ci] to prevent recursion"
    assert "git pull --rebase" in commit_script, "Must rebase before push to handle concurrent repo updates"
    assert "git push origin master" in commit_script, "Must push to master branch"
