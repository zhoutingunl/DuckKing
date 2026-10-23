import json

import httpx
import pytest

from duckking.config import Settings
from duckking.onboarding import PROMPT, main, setup_device


def platform(tmp_path, agents=None, bound=False, failure=None, created="duck-agent"):
    key = tmp_path / "key"
    key.write_text("test-platform-key")
    calls = []
    state = {"bound": bound}

    def respond(request):
        path = request.url.path
        calls.append(
            (request.method, path, json.loads(request.content) if request.content else None)
        )
        if path == "/v1/ota/":
            assert "Authorization" not in request.headers
            return httpx.Response(
                200,
                json={"websocket": {"url": "wss://example.com/ws", "token": "device-test"}}
                if state["bound"]
                else {"activation": {"code": "123456"}},
            )
        assert request.headers["Authorization"] == "Bearer test-platform-key"
        if failure:
            return httpx.Response(200, json={"code": failure})
        if path == "/xiaozhi/agent/list":
            data = [] if agents is None else agents
        elif path == "/xiaozhi/agent":
            body = json.loads(request.content)
            assert body["intentModelId"] == "Intent_function_call"
            assert body["agentName"] == "DuckKing"
            data = created
        else:
            assert path == "/xiaozhi/device/bind/duck-agent/123456"
            state["bound"] = True
            data = {}
        return httpx.Response(200, json={"code": 0, "data": data})

    return key, calls, httpx.AsyncClient(transport=httpx.MockTransport(respond))


async def test_creates_agent_binds_device_and_never_sends_platform_key_to_ota(tmp_path):
    key, calls, http = platform(tmp_path)
    async with http:
        result = await setup_device(
            Settings(data_dir=tmp_path / "state"), key, model_id="test-model", http=http
        )
    assert result["status"] == "ready"
    assert (
        next(body for _, path, body in calls if path == "/xiaozhi/agent")["llmModelId"]
        == "test-model"
    )
    saved = tmp_path / "state" / "onboarding.json"
    assert saved.stat().st_mode & 0o777 == 0o600
    assert "test-platform-key" not in saved.read_text()


@pytest.mark.parametrize("explicit", [False, True])
async def test_reuses_named_or_explicit_agent_without_overwriting_it(tmp_path, explicit):
    key, calls, http = platform(tmp_path, agents=[{"id": "duck-agent", "agentName": "DuckKing"}])
    async with http:
        result = await setup_device(
            Settings(data_dir=tmp_path / "state"),
            key,
            agent_id="duck-agent" if explicit else None,
            http=http,
        )
    assert result["status"] == "ready"
    assert not any(method == "POST" and path == "/xiaozhi/agent" for method, path, _ in calls)


async def test_already_bound_device_is_not_migrated(tmp_path):
    key, calls, http = platform(tmp_path, bound=True)
    async with http:
        result = await setup_device(Settings(data_dir=tmp_path / "state"), key, http=http)
    assert result["status"] == "already_bound"
    assert not any("/device/bind/" in path for _, path, _ in calls)


@pytest.mark.parametrize(
    "options,agent_id",
    [
        ({"failure": 401}, None),
        ({"agents": {}}, None),
        ({"created": None}, None),
        ({}, "not-owned"),
        (
            {
                "agents": [
                    {"id": "a", "agentName": "DuckKing"},
                    {"id": "b", "agentName": "DuckKing"},
                ]
            },
            None,
        ),
    ],
)
async def test_ambiguous_or_invalid_platform_state_fails(tmp_path, options, agent_id):
    key, _, http = platform(tmp_path, **options)
    async with http:
        with pytest.raises(ValueError):
            await setup_device(
                Settings(data_dir=tmp_path / "state"), key, agent_id=agent_id, http=http
            )


@pytest.mark.parametrize("content", ["", "two\nlines"])
async def test_key_file_must_be_nonempty_and_one_line(tmp_path, content):
    key = tmp_path / "key"
    key.write_text(content)
    with pytest.raises(ValueError):
        await setup_device(Settings(data_dir=tmp_path), key)


async def test_owned_http_client_is_closed(tmp_path, monkeypatch):
    key, _, http = platform(tmp_path)
    monkeypatch.setattr("duckking.onboarding.httpx.AsyncClient", lambda **kwargs: http)
    await setup_device(Settings(data_dir=tmp_path / "state"), key)
    assert http.is_closed


def test_cli_prints_only_result_and_sanitizes_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["duckking-setup", "--key-file", str(tmp_path / "key")])
    monkeypatch.setattr("duckking.onboarding.Settings.load", lambda: Settings(data_dir=tmp_path))

    async def success(*args, **kwargs):
        return {"status": "ready"}

    monkeypatch.setattr("duckking.onboarding.setup_device", success)
    main()
    assert json.loads(capsys.readouterr().out)["status"] == "ready"

    async def failed(*args, **kwargs):
        raise ValueError("a-private-key-that-must-not-appear")

    monkeypatch.setattr("duckking.onboarding.setup_device", failed)
    with pytest.raises(SystemExit) as error:
        main()
    assert "a-private-key" not in str(error.value)


@pytest.mark.parametrize("mode", ["updated", "current", "unreadable", "verify_failed"])
async def test_prompt_sync_backs_up_and_updates_only_prompt_without_binding(tmp_path, mode):
    key = tmp_path / "key"
    key.write_text("test-key")
    before = PROMPT if mode == "current" else "original dedicated DuckKing instructions"
    state = {"systemPrompt": before, "llmModelId": "unchanged-model"}
    calls = []

    def respond(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/xiaozhi/agent/list":
            data = [{"id": "duck", "agentName": "DuckKing"}]
        else:
            assert request.url.path == "/xiaozhi/agent/duck"
            if request.method == "PUT":
                assert json.loads(request.content) == {"systemPrompt": PROMPT}
                if mode != "verify_failed":
                    state.update(systemPrompt=PROMPT)
            data = None if mode == "unreadable" else dict(state)
        return httpx.Response(200, json={"code": 0, "data": data})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        if mode in {"unreadable", "verify_failed"}:
            with pytest.raises(ValueError):
                await setup_device(Settings(data_dir=tmp_path), key, http=http, sync_prompt=True)
        else:
            result = await setup_device(
                Settings(data_dir=tmp_path), key, http=http, sync_prompt=True
            )
            assert result == {"status": f"prompt_{mode}"}
    backups = list(tmp_path.glob("prompt-backup-*.txt"))
    assert len(backups) == (1 if mode in {"updated", "verify_failed"} else 0)
    for backup in backups:
        assert backup.read_text() == before
        assert backup.stat().st_mode & 0o777 == 0o600
    assert not any("/device/" in path or "/ota/" in path for _, path in calls)


@pytest.mark.parametrize(
    "agents,agent_id", [([], None), ([{"id": "a", "agentName": "Other"}], "a")]
)
async def test_prompt_sync_does_not_create_agents_or_modify_unrelated_agents(
    tmp_path, agents, agent_id,
):
    key, calls, http = platform(tmp_path, agents=agents)
    async with http:
        with pytest.raises(ValueError):
            await setup_device(
                Settings(data_dir=tmp_path), key, agent_id=agent_id, http=http, sync_prompt=True
            )
    assert all(method == "GET" for method, _, _ in calls)
