"""Visitor region to default language: local ipdb lookup, fails closed to zh."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duckking.app import create_app
from duckking.geo import RegionResolver, extract_client_ip, is_public_ip, language_for


def test_language_rule_is_geographic_europe_excluding_britain():
    assert language_for("FR") == "fr"
    assert language_for("DE") == "fr"
    assert language_for("CH") == "fr"  # 非欧盟但属地理欧洲
    assert language_for("CY") == "fr"
    assert language_for("GB") == "zh"  # 用户明确排除英国
    assert language_for("US") == "zh"
    assert language_for("JP") == "zh"
    assert language_for(None) == "zh"
    assert language_for("") == "zh"


def test_client_ip_prefers_last_forwarded_hop_added_by_the_trusted_proxy():
    # 生产拓扑只有一个可信代理（OpenResty）：末跳是代理追加/背书的真实访客 IP，
    # 访客自带伪造 XFF 或隐私插件注入的垃圾值排在前面，不应被采信。
    assert extract_client_ip("1.2.3.4, 212.27.48.10", "127.0.0.1") == "212.27.48.10"
    assert extract_client_ip("junk-without-ip, 212.27.48.10", "127.0.0.1") == "212.27.48.10"
    assert extract_client_ip("212.27.48.10", "127.0.0.1") == "212.27.48.10"
    assert extract_client_ip(None, "127.0.0.1") == "127.0.0.1"
    assert extract_client_ip("", None) is None
    assert extract_client_ip("   ", "127.0.0.1") == "127.0.0.1"


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
    resolver = RegionResolver(None, french_room="2", lookup=lambda ip: "FR")
    result = resolver.resolve({"x-forwarded-for": "212.27.48.10"}, None)
    assert result.public() == {"language": "fr", "region": "FR", "room": "2"}
    assert "ip" not in result.public() and "client" not in result.public()


def test_gateway_country_header_short_circuits_database():
    calls = []

    def fake_lookup(ip):
        calls.append(ip)

    resolver = RegionResolver(None, country_header="cf-ipcountry", lookup=fake_lookup)
    result = resolver.resolve({"cf-ipcountry": "de"}, None)
    assert result.public() == {"language": "fr", "region": "DE", "room": None}
    assert calls == []


def test_failing_lookup_falls_back_to_default_language():
    def broken(ip):
        raise RuntimeError("db offline")

    resolver = RegionResolver(None, lookup=broken)
    result = resolver.resolve({"x-forwarded-for": "212.27.48.10"}, None)
    assert result.public() == {"language": "zh", "region": None, "room": None}


def test_missing_database_directory_still_serves_default_language(tmp_path):
    resolver = RegionResolver(tmp_path / "absent")
    result = resolver.resolve({"x-forwarded-for": "212.27.48.10"}, None)
    assert result.public() == {"language": "zh", "region": None, "room": None}


def test_ui_preferences_endpoint_uses_resolver_result_without_exposing_ip():
    app = create_app()
    app.state.region = RegionResolver(None, french_room="2", lookup=lambda ip: "FR")
    with TestClient(app) as client:
        response = client.get("/api/ui-preferences", headers={"X-Forwarded-For": "212.27.48.10"})
    assert response.status_code == 200
    assert response.json() == {"language": "fr", "region": "FR", "room": "2"}
    assert response.headers["cache-control"] == "no-store"


def test_ui_preferences_endpoint_defaults_to_chinese_without_a_public_ip():
    with TestClient(create_app()) as client:
        response = client.get("/api/ui-preferences")
    assert response.status_code == 200
    assert response.json() == {"language": "zh", "region": None, "room": None}


GEO_DIR = Path(
    __import__("os").environ.get("DUCKKING_GEO_DB_DIR", "~/.local/share/duckking/geo")
).expanduser()


@pytest.mark.skipif(not (GEO_DIR / "neo.ipv4.ipdb").exists(), reason="本地未放置 ipdb 地址库")
def test_real_database_resolves_france_and_excludes_britain():
    resolver = RegionResolver(GEO_DIR)
    assert resolver.resolve({"x-forwarded-for": "212.27.48.10"}, None).language == "fr"
    assert resolver.resolve({"x-forwarded-for": "51.140.62.30"}, None).language == "zh"
    assert resolver.resolve({"x-forwarded-for": "192.168.1.5"}, None).language == "zh"
