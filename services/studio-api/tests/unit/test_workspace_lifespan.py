"""Constructing an app must not dispatch work; its lifespan owns workers."""

from fastapi.testclient import TestClient

from studio.api.app import create_app
from studio.config.settings import Settings


def test_learning_worker_starts_and_stops_with_application_lifespan(monkeypatch):
    from studio.domain.learning.workspace_runtime.dispatcher import LearningDispatcher

    calls = []
    monkeypatch.setattr(LearningDispatcher, "start", lambda _self: calls.append("start"))
    monkeypatch.setattr(LearningDispatcher, "shutdown", lambda _self: calls.append("stop"))
    # This test isolates the lifespan from the separately tested agent dispatcher.
    monkeypatch.setattr(
        "studio.domain.agent_workspace.runtime.start_agent_worker", lambda app: None
    )
    app = create_app(Settings())
    assert calls == []
    with TestClient(app):
        assert calls == ["start"]
    assert calls == ["start", "stop"]
