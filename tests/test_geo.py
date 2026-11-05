"""Visitor region to default language: local ipdb lookup, fails closed to zh."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import duckking.app as app_module
from duckking.app import create_app
from duckking.geo import RegionResolver, extract_client_ip, is_public_ip, language_for


def test_language_rule_is_geographic_europe_excluding_britain():
    assert language_for("FR") == "fr"
    assert language_for("DE") == "fr"
    assert language_for("CH") == "fr"  # 非欧盟但属地理欧洲
    assert language_for("CY") == "fr"
    assert language_for("GB") == "en"  # 美国/英国默认英语
    assert language_for("US") == "en"
    assert language_for("CA") == "zh"  # 未指定的英语国家仍回退中文
    assert language_for("JP") == "zh"
    assert language_for(None) == "zh"
    assert language_for("") == "zh"


def test_forwarded_ip_is_used_only_from_a_configured_proxy():
    proxies = ("10.70.0.0/16",)
    assert extract_client_ip("1.2.3.4, 212.27.48.10", "10.70.56.34", proxies) == "212.27.48.10"
    assert extract_client_ip("junk, 212.27.48.10", "10.70.56.34", proxies) == "212.27.48.10"
    # A direct client cannot choose somebody else's region via a forged XFF.
    assert extract_client_ip("212.27.48.10", "51.140.62.30", proxies) is None
    assert extract_client_ip(None, "51.140.62.30", proxies) == "51.140.62.30"
    assert extract_client_ip(None, "10.70.56.34", proxies) is None
    assert extract_client_ip("", None, proxies) is None


def test_untrusted_forwarded_ip_cannot_select_french_language_or_room():
    calls = []
    resolver = RegionResolver(
        None,
        french_rooms=("2", "3"),
        trusted_proxies=("10.70.0.0/16",),
        lookup=lambda ip: calls.append(ip) or {"212.27.48.10": "FR", "51.140.62.30": "GB"}[ip],
    )
    spoofed = resolver.resolve({"x-forwarded-for": "212.27.48.10"}, "51.140.62.30")
    assert spoofed.public() == {
        "language": "zh",
        "region": None,
        "french_voice_available": True,
        "english_voice_available": False,
    }
    direct = resolver.resolve({}, "51.140.62.30")
    assert direct.language == "en" and direct.region == "GB"
    forwarded = resolver.resolve({"x-forwarded-for": "192.168.1.1, 212.27.48.10"}, "10.70.56.34")
    assert forwarded.language == "fr" and forwarded.region == "FR"
    assert calls == ["51.140.62.30", "212.27.48.10"]


def test_is_public_ip_rejects_private_and_malformed_input():
    assert is_public_ip("212.27.48.10")
    assert not is_public_ip("192.168.1.5")
    assert not is_public_ip("127.0.0.1")
    assert not is_public_ip("203.0.113.9")  # TEST-NET-3,非全球可路由
    assert not is_public_ip("not-an-ip")
    assert not is_public_ip(None)
    assert not is_public_ip("")


def test_private_loopback_and_malformed_addresses_skip_lookup():
    calls = []
    resolver = RegionResolver(None, lookup=lambda ip: calls.append(ip) or "FR")
    cases = [
        ({"x-forwarded-for": "192.168.1.5"}, None),
        ({}, "127.0.0.1"),
        ({"x-forwarded-for": "not-an-ip"}, None),
        ({}, None),
    ]
    for headers, host in cases:
        assert resolver.resolve(headers, host).language == "zh"
    assert calls == []


def test_public_ip_resolves_french_language_with_room_and_payload_has_no_ip():
    resolver = RegionResolver(
        None,
        french_rooms=("2", "3"),
        trusted_proxies=("10.70.0.0/16",),
        lookup=lambda ip: "FR",
    )
    result = resolver.resolve({"x-forwarded-for": "212.27.48.10"}, "10.70.56.34")
    assert result.public() == {
        "language": "fr",
        "region": "FR",
        "french_voice_available": True,
        "english_voice_available": False,
    }
    assert "ip" not in result.public() and "client" not in result.public()


def test_us_and_britain_resolve_english_with_english_rooms():
    resolver = RegionResolver(
        None,
        english_rooms=("4",),
        trusted_proxies=("10.70.0.0/16",),
        lookup=lambda ip: {"8.8.8.8": "US", "51.140.62.30": "GB"}[ip],
    )
    us = resolver.resolve({"x-forwarded-for": "8.8.8.8"}, "10.70.56.34")
    assert us.public() == {
        "language": "en",
        "region": "US",
        "french_voice_available": False,
        "english_voice_available": True,
    }
    gb = resolver.resolve({"x-forwarded-for": "51.140.62.30"}, "10.70.56.34")
    assert gb.language == "en" and gb.region == "GB"


def test_gateway_country_header_short_circuits_database():
    calls = []

    def fake_lookup(ip):
        calls.append(ip)

    resolver = RegionResolver(
        None,
        country_header="cf-ipcountry",
        trusted_proxies=("10.70.0.0/16",),
        lookup=fake_lookup,
    )
    result = resolver.resolve({"cf-ipcountry": "de"}, "10.70.56.34")
    assert result.public() == {
        "language": "fr",
        "region": "DE",
        "french_voice_available": False,
        "english_voice_available": False,
    }
    assert calls == []


def test_untrusted_peer_cannot_forge_a_gateway_country_header():
    resolver = RegionResolver(
        None,
        country_header="cf-ipcountry",
        trusted_proxies=("10.70.0.0/16",),
        french_rooms=("2",),
        lookup=lambda ip: "GB",
    )
    result = resolver.resolve({"cf-ipcountry": "FR"}, "51.140.62.30")
    assert result.public() == {
        "language": "zh",
        "region": None,
        "french_voice_available": True,
        "english_voice_available": False,
    }
    trusted = resolver.resolve({"cf-ipcountry": "US"}, "10.70.56.34")
    assert trusted.public() == {
        "language": "en",
        "region": "US",
        "french_voice_available": True,
        "english_voice_available": False,
    }


def test_failing_lookup_falls_back_to_default_language():
    def broken(ip):
        raise RuntimeError("db offline")

    resolver = RegionResolver(None, trusted_proxies=("10.70.0.0/16",), lookup=broken)
    result = resolver.resolve({"x-forwarded-for": "212.27.48.10"}, "10.70.56.34")
    assert result.public() == {
        "language": "zh",
        "region": None,
        "french_voice_available": False,
        "english_voice_available": False,
    }


def test_missing_database_directory_still_serves_default_language(tmp_path):
    resolver = RegionResolver(tmp_path / "absent")
    result = resolver.resolve({"x-forwarded-for": "212.27.48.10"}, "127.0.0.1")
    assert result.public() == {
        "language": "zh",
        "region": None,
        "french_voice_available": False,
        "english_voice_available": False,
    }


def test_ui_preferences_endpoint_uses_resolver_result_without_exposing_ip():
    app = create_app()
    app.state.region = RegionResolver(
        None,
        french_rooms=("2", "3"),
        trusted_proxies=("127.0.0.0/8",),
        lookup=lambda ip: "FR",
    )
    with TestClient(app, client=("127.0.0.1", 1234)) as client:
        response = client.get("/api/ui-preferences", headers={"X-Forwarded-For": "212.27.48.10"})
    assert response.status_code == 200
    assert response.json() == {
        "language": "fr",
        "region": "FR",
        "french_voice_available": True,
        "english_voice_available": False,
    }
    assert response.headers["cache-control"] == "no-store"


def test_ui_preferences_uses_configured_socket_peer_to_trust_forwarded_ip(tmp_path):
    from duckking.config import Settings

    settings = Settings(data_dir=tmp_path, geo_trusted_proxies=("10.70.0.0/16",))
    app = create_app(settings=settings)
    app.state.region = RegionResolver(
        None,
        french_rooms=("2",),
        trusted_proxies=settings.geo_trusted_proxies,
        lookup=lambda ip: "FR",
    )
    with TestClient(app, client=("10.70.56.34", 1234)) as client:
        response = client.get("/api/ui-preferences", headers={"X-Forwarded-For": "212.27.48.10"})
    assert response.status_code == 200
    assert response.json() == {
        "language": "fr",
        "region": "FR",
        "french_voice_available": True,
        "english_voice_available": False,
    }


def test_ui_preferences_endpoint_defaults_to_chinese_without_a_public_ip():
    with TestClient(create_app()) as client:
        response = client.get("/api/ui-preferences")
    assert response.status_code == 200
    assert response.json() == {
        "language": "zh",
        "region": None,
        "french_voice_available": False,
        "english_voice_available": False,
    }


def test_direct_request_cannot_forge_a_forwarded_client_country():
    calls = []
    app = create_app()
    app.state.region = RegionResolver(
        None,
        country_header="cf-ipcountry",
        french_rooms=("2",),
        trusted_proxies=("10.70.0.0/16",),
        lookup=lambda ip: calls.append(ip) or "GB",
    )
    with TestClient(app, client=("51.140.62.30", 1234)) as client:
        response = client.get(
            "/api/ui-preferences",
            headers={"X-Forwarded-For": "212.27.48.10", "CF-IPCountry": "FR"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "language": "zh",
        "region": None,
        "french_voice_available": True,
        "english_voice_available": False,
    }
    assert calls == []


def test_cli_does_not_allow_uvicorn_to_rewrite_the_socket_peer(monkeypatch):
    options = {}
    monkeypatch.setattr("sys.argv", ["duckking"])
    monkeypatch.setattr(app_module, "create_app", lambda *args, **kwargs: object())
    monkeypatch.setattr(app_module.uvicorn, "run", lambda app, **kwargs: options.update(kwargs))
    app_module.main()
    assert options["proxy_headers"] is False
    assert options["access_log"] is False


GEO_DIR = Path(
    __import__("os").environ.get("DUCKKING_GEO_DB_DIR", "~/.local/share/duckking/geo")
).expanduser()


@pytest.mark.skipif(not (GEO_DIR / "neo.ipv4.ipdb").exists(), reason="本地未放置 ipdb 地址库")
def test_real_database_resolves_france_britain_and_the_us():
    resolver = RegionResolver(GEO_DIR, trusted_proxies=("10.70.0.0/16",))
    assert resolver.resolve({"x-forwarded-for": "212.27.48.10"}, "10.70.56.34").language == "fr"
    assert resolver.resolve({"x-forwarded-for": "51.140.62.30"}, "10.70.56.34").language == "en"
    assert resolver.resolve({"x-forwarded-for": "192.168.1.5"}, "10.70.56.34").language == "zh"
