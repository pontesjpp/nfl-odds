import os
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
import pytest
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


def test_repo_info_and_branch_helpers(monkeypatch):
    monkeypatch.setenv("GITHUB_REPO_OWNER", "testowner")
    monkeypatch.setenv("GITHUB_REPO_NAME", "testrepo")
    monkeypatch.setenv("GITHUB_BRANCH", "dev-branch")

    owner, repo = get_github_repo_info()
    assert owner == "testowner"
    assert repo == "testrepo"
    assert get_github_branch() == "dev-branch"


def test_trigger_workflow_unauthorized_returns_403(client):
    # No auth header
    res = client.post("/api/trigger-workflow", json={"week": 2})
    assert res.status_code == 403
    assert "Administrador" in res.json()["detail"]


def test_trigger_workflow_missing_token_returns_400(client, admin_headers, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_PAT", raising=False)
    monkeypatch.delenv("GITHUB_PAT", raising=False)

    res = client.post("/api/trigger-workflow", headers=admin_headers, json={"week": 2})
    assert res.status_code == 400
    assert "GITHUB_TOKEN não configurado" in res.json()["detail"]


@pytest.mark.parametrize(
    "gh_status,expected_status,expected_keyword",
    [
        (401, 401, "Token do GitHub inválido"),
        (403, 403, "actions:write"),
        (404, 404, "não encontrado no branch"),
        (422, 422, "Parâmetros de workflow inválidos"),
    ],
)
def test_trigger_workflow_github_error_mappings(
    client, admin_headers, monkeypatch, gh_status, expected_status, expected_keyword
):
    monkeypatch.setenv("GITHUB_TOKEN", "mock_valid_token_string")

    mock_resp = MagicMock()
    mock_resp.status_code = gh_status
    mock_resp.text = '{"message": "GitHub API simulated response"}'
    mock_resp.json.return_value = {"message": "GitHub API simulated response"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = client.post(
            "/api/trigger-workflow",
            headers=admin_headers,
            json={"week": 3, "fast": True},
        )
        assert res.status_code == expected_status
        assert expected_keyword in res.json()["detail"]


def test_trigger_workflow_network_error_returns_502(client, admin_headers, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        res = client.post(
            "/api/trigger-workflow",
            headers=admin_headers,
            json={"week": 2},
        )
        assert res.status_code == 502
        assert "Falha de rede" in res.json()["detail"]


def test_trigger_workflow_success_returns_200_and_links(client, admin_headers, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")
    monkeypatch.setenv("GITHUB_REPO_OWNER", "pontesjpp")
    monkeypatch.setenv("GITHUB_REPO_NAME", "nfl-odds")
    monkeypatch.setenv("GITHUB_BRANCH", "master")

    # Mock dispatch POST (returns 204 No Content)
    mock_dispatch_resp = MagicMock()
    mock_dispatch_resp.status_code = 204

    # Mock runs GET (returns 200 with recent run)
    mock_runs_resp = MagicMock()
    mock_runs_resp.status_code = 200
    mock_runs_resp.json.return_value = {
        "workflow_runs": [
            {
                "id": 987654321,
                "html_url": "https://github.com/pontesjpp/nfl-odds/actions/runs/987654321",
                "status": "queued",
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.return_value = mock_dispatch_resp
        mock_get.return_value = mock_runs_resp

        res = client.post(
            "/api/trigger-workflow",
            headers=admin_headers,
            json={"week": 2, "fast": False},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["run_id"] == 987654321
        assert "actions/runs/987654321" in data["run_url"]
        assert "update_odds.yml" in data["actions_url"]
        assert data["branch"] == "master"


def test_workflow_status_polling_by_run_id(client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": 12345,
        "status": "completed",
        "conclusion": "success",
        "html_url": "https://github.com/pontesjpp/nfl-odds/actions/runs/12345",
        "created_at": "2026-09-18T00:00:00Z",
        "updated_at": "2026-09-18T00:05:00Z",
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = client.get("/api/workflow-status?run_id=12345")
        assert res.status_code == 200
        data = res.json()
        assert data["run_id"] == 12345
        assert data["status"] == "completed"
        assert data["conclusion"] == "success"


def test_workflow_status_polling_latest_runs(client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "workflow_runs": [
            {
                "id": 55555,
                "status": "in_progress",
                "conclusion": None,
                "html_url": "https://github.com/pontesjpp/nfl-odds/actions/runs/55555",
                "created_at": "2026-09-18T00:10:00Z",
                "updated_at": "2026-09-18T00:11:00Z",
            }
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = client.get("/api/workflow-status")
        assert res.status_code == 200
        data = res.json()
        assert data["run_id"] == 55555
        assert data["status"] == "in_progress"
        assert data["conclusion"] is None


def test_run_pipeline_auto_delegation_when_token_present(client, admin_headers, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "mock_token")

    mock_dispatch_resp = MagicMock()
    mock_dispatch_resp.status_code = 204

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.return_value = mock_dispatch_resp
        mock_runs_resp = MagicMock()
        mock_runs_resp.status_code = 200
        mock_runs_resp.json.return_value = {"workflow_runs": []}
        mock_get.return_value = mock_runs_resp

        # Calling /api/run-pipeline should auto-delegate to GitHub Actions
        res = client.post("/api/run-pipeline", headers=admin_headers)
        assert res.status_code == 200
        assert res.json()["status"] == "success"
        assert "disparado com sucesso" in res.json()["message"]
