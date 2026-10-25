import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from duckking.app import create_app, main
from duckking.deployment import DeploymentStatus


def release():
    return dict(
        version="test-release",
        commit="a" * 40,
        built_at="2026-10-24T00:00:00Z",
        operator="test",
        git_ref="test-ref",
        target="test-host",
    )


def test_running_release_is_immutable_and_history_never_exposes_extra_fields(tmp_path):
    metadata, history = tmp_path / "release.json", tmp_path / "history.jsonl"
    metadata.write_text(json.dumps(release() | {"token": "private"}))
    deployment = DeploymentStatus(metadata, history)
    assert deployment.snapshot()["state"] == "unrecorded"
    metadata.write_text(json.dumps(release() | {"version": "other-release"}))
    history.write_text(json.dumps(release() | {"status": "success", "token": "private"}) + "\n")
    state = deployment.snapshot()
    assert state["state"] == "ok" and state["current"]["version"] == "test-release"
    assert "private" not in json.dumps(state)
    history.write_text(json.dumps(release() | {"status": "staged"}) + "\n")
    assert deployment.snapshot()["state"] == "staged"
    history.write_text(json.dumps(release() | {"status": "success", "commit": "b" * 40}) + "\n")
    assert deployment.snapshot()["state"] == "mismatch"


def test_missing_invalid_and_bounded_release_records(tmp_path):
    metadata, history = tmp_path / "release.json", tmp_path / "history.jsonl"
    assert DeploymentStatus(metadata, history).snapshot()["state"] == "development"
    metadata.write_text('{"version":7}')
    history.write_text(
        "invalid\n"
        + "\n".join(
            json.dumps(release() | {"status": "failed", "version": f"r{i}"}) for i in range(110)
        )
    )
    state = DeploymentStatus(metadata, history).snapshot()
    assert state["state"] == "unknown" and len(state["records"]) == 100
    assert state["records"][0]["version"] == "r109"
    assert "部分部署记录损坏" in state["warnings"]


def test_public_host_is_explicit_and_foreign_origins_remain_rejected():
    app = create_app(allowed_hosts=["ztmonitor.qbox.net"])
    with TestClient(app, base_url="https://ztmonitor.qbox.net") as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/deployments").headers["cache-control"] == "no-store"
        assert client.get("/api/health", headers={"Host": "untrusted.example"}).status_code == 400
        assert (
            client.post(
                "/api/actions",
                json={"name": "stop"},
                headers={"Origin": "https://untrusted.example"},
            ).status_code
            == 403
        )
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "wss://ztmonitor.qbox.net/scene-ws?room=1", headers={"Origin": "https://untrusted.example"}
            ):
                pass
        with client.websocket_connect(
            "wss://ztmonitor.qbox.net/scene-ws?room=1", headers={"Origin": "https://ztmonitor.qbox.net"}
        ) as ws:
            assert ws.receive_json()["type"] == "not_started"


@pytest.mark.parametrize(
    "option,value",
    [
        ("--allowed-host", "*"),
        ("--allowed-host", "https://example.com"),
        ("--root-path", "//evil.example"),
        ("--root-path", "/duckking/"),
    ],
)
def test_cli_rejects_unbounded_hosts_and_ambiguous_prefixes(monkeypatch, option, value):
    monkeypatch.setattr("sys.argv", ["duckking", option, value])
    with pytest.raises(SystemExit):
        main()


def test_cli_configures_proxy_prefix_without_changing_loopback_binding(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "sys.argv", ["duckking", "--allowed-host", "ztmonitor.qbox.net", "--root-path", "/duckking"]
    )
    monkeypatch.setattr("duckking.app.uvicorn.run", lambda app, **kw: captured.update(kw))
    main()
    assert captured == {"host": "127.0.0.1", "port": 8765, "root_path": "/duckking"}
