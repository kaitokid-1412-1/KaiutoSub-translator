"""Global pytest fixtures."""

import threading
import time
from pathlib import Path
import httpx
import pytest
import uvicorn

from tests.mock_llm import MockLLMConfig, create_mock_llm_app


@pytest.fixture(scope="session")
def mock_server():
    mock_cfg = MockLLMConfig()
    app = create_mock_llm_app(mock_cfg)
    port = 20199
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # Wait for ready
    ready = False
    for _ in range(50):
        try:
            with httpx.Client(timeout=1.0, trust_env=False) as client:
                r = client.get(f"http://127.0.0.1:{port}/models")
                if r.status_code == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.1)

    assert ready, "Mock server failed to start"
    yield f"http://127.0.0.1:{port}", mock_cfg
    server.should_exit = True
