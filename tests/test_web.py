"""Unit and security tests for local Web UI server."""

import secrets
from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from subtrans.core.config import Config
from subtrans.web.server import create_app


@pytest.fixture
def test_app():
    cfg = Config()
    cfg.provider.api_key = "sk-supersecretkey12345"
    token = "test_secret_token_123"
    app = create_app(token=token, config=cfg)
    return app, token


def test_web_security_bad_host(test_app):
    app, token = test_app
    client = TestClient(app)

    # Bad host header
    resp = client.get("/", headers={"Host": "malicious.com"})
    assert resp.status_code == 403
    assert "Host" in resp.json()["detail"]


def test_web_security_bad_origin(test_app):
    app, token = test_app
    client = TestClient(app)

    # Bad origin header
    resp = client.get("/", headers={"Host": "127.0.0.1", "Origin": "http://attacker.com"})
    assert resp.status_code == 403
    assert "Origin" in resp.json()["detail"]


def test_web_security_missing_token_on_post(test_app):
    app, token = test_app
    client = TestClient(app)

    # POST without token must be rejected with 403
    resp = client.post("/api/scan", json={"path": "."}, headers={"Host": "127.0.0.1"})
    assert resp.status_code == 403
    assert "توکن" in resp.json()["detail"]


def test_web_security_valid_token_succeeds(test_app):
    app, token = test_app
    client = TestClient(app)

    # POST with valid X-SubTrans-Token header
    resp = client.post(
        "/api/scan",
        json={"path": "."},
        headers={"Host": "127.0.0.1", "X-SubTrans-Token": token},
    )
    assert resp.status_code == 200
    assert "files" in resp.json()


def test_api_key_masked_in_config(test_app):
    app, token = test_app
    client = TestClient(app)

    # GET /api/config requires token
    resp = client.get(
        "/api/config",
        headers={"Host": "127.0.0.1", "X-SubTrans-Token": token},
    )
    assert resp.status_code == 200
    data = resp.json()
    masked_key = data["provider"]["api_key"]
    # Key should be masked, never returning raw "sk-supersecretkey12345"
    assert masked_key != "sk-supersecretkey12345"
    assert "..." in masked_key or "********" in masked_key


def test_static_files_served_locally(test_app):
    app, token = test_app
    client = TestClient(app)

    # Root HTML
    resp_html = client.get(f"/?token={token}", headers={"Host": "127.0.0.1"})
    assert resp_html.status_code == 200
    assert "SubTrans Auto" in resp_html.text

    # CSS static file
    resp_css = client.get("/static/style.css", headers={"Host": "127.0.0.1"})
    assert resp_css.status_code == 200
    assert "--bg-color" in resp_css.text

    # JS static file
    resp_js = client.get("/static/app.js", headers={"Host": "127.0.0.1"})
    assert resp_js.status_code == 200
    assert "SubTrans Auto" in resp_js.text


def test_status_endpoint(test_app):
    app, token = test_app
    client = TestClient(app)

    resp = client.get("/api/status", headers={"Host": "127.0.0.1"})
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "job_id" in data
    assert data["status"] in ("IDLE", "RUNNING", "COMPLETED", "FAILED")


def test_sse_events(test_app):
    app, token = test_app
    client = TestClient(app)

    # Connecting with token and x-test-once header returns initial init event
    resp = client.get(
        f"/api/events?token={token}",
        headers={"Host": "127.0.0.1", "X-Test-Once": "true"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    assert "init" in resp.text
    assert token in resp.text
