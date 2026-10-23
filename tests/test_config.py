import json
import uuid

import httpx
import pytest

from duckking.config import Settings, provision, validate_endpoint


def test_identity_is_private_stable_and_distinct_from_credentials(tmp_path):
    settings = Settings(data_dir=tmp_path)
    identity = settings.identity()
    assert settings.identity() == identity
    assert uuid.UUID(identity["client_id"]).version == 4
    assert (tmp_path / "identity.json").stat().st_mode & 0o777 == 0o600
    assert "ws_token" not in json.loads((tmp_path / "identity.json").read_text())
    assert "never-print-this" not in repr(Settings(ws_token="never-print-this"))


def test_settings_load_scoped_secrets_and_environment_overrides(tmp_path, monkeypatch):
    secrets = tmp_path / "duckking.env"
    secrets.write_text("LINX_WS_TOKEN=test-only\nLINX_WS_URL=wss://example.com/ws\n")
    monkeypatch.setenv("DUCKKING_SECRETS_FILE", str(secrets))
    monkeypatch.setenv("DUCKKING_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("LINX_WS_TOKEN", "override")
    assert Settings.load().ws_token == "override"
    secrets.unlink()
    assert Settings.load().data_dir == tmp_path / "state"


@pytest.mark.parametrize("values", [{"device_id": "not-a-mac"}, {"client_id": str(uuid.uuid1())}])
def test_bad_identity_overrides_are_rejected(tmp_path, values):
    with pytest.raises(ValueError):
        Settings(data_dir=tmp_path, **values).identity()


@pytest.mark.parametrize(
    "url,ws",
    [
        ("https://example.com/ota", False),
        ("http://127.0.0.1:123/ota", False),
        ("wss://example.com/ws", True),
        ("ws://localhost:123/ws", True),
    ],
)
def test_endpoint_validation_allows_tls_and_local_tests(url, ws):
    validate_endpoint(url, websocket=ws)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/ota",
        "https://user:pass@example.com/",
        "https:///missing",
        "https://example.com/#fragment",
    ],
)
def test_unsafe_or_ambiguous_endpoints_are_rejected(url):
    with pytest.raises(ValueError):
        validate_endpoint(url)


async def test_ota_request_and_activation_then_bound_response(tmp_path):
    count = 0

    def handler(request):
        nonlocal count
        body = json.loads(request.content)
        assert body["mac_address"] == request.headers["Device-Id"]
        assert body["uuid"] == request.headers["Client-Id"]
        assert request.headers["Activation-Version"] == "1"
        count += 1
        return httpx.Response(
            200,
            json={"activation": {"code": "123456"}}
            if count == 1
            else {"websocket": {"url": "wss://example.com/ws", "token": "test"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        settings = Settings(data_dir=tmp_path)
        assert (await provision(settings, http))["activation"]["code"] == "123456"
        assert (await provision(settings, http))["websocket"]["token"] == "test"


async def test_manual_device_credentials_and_ota_failures(tmp_path):
    settings = Settings(data_dir=tmp_path, ws_url="wss://example.com/ws", ws_token="test")
    assert (await provision(settings, None))["websocket"]["token"] == "test"
    for response, error in [
        (httpx.Response(401), httpx.HTTPStatusError),
        (httpx.Response(200, json=[]), ValueError),
    ]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r, response=response: response)
        ) as http:
            with pytest.raises(error):
                await provision(Settings(data_dir=tmp_path), http)
