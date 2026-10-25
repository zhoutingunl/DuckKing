import base64
import gzip
import json
import logging
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from duckking import model_assets
from duckking.app import create_app

ASSETS = Path(__file__).resolve().parents[1] / "external"


def test_binary_asset_preserves_all_official_vertices_faces_rig_and_materials():
    original = model_assets.official_preview(ASSETS)
    asset = model_assets.visual_asset(ASSETS)
    raw = gzip.decompress(asset.compressed)
    assert raw[:4] == b"DKM1" and len(raw) == asset.decoded_bytes
    size = struct.unpack_from("<I", raw, 4)[0]
    meta = json.loads(raw[8:8 + size])
    start = 8 + (size + 3) // 4 * 4
    meshes = meta.pop("meshes")
    assert meta == {k: v for k, v in original.items() if k != "meshes"}
    for key, mesh in meshes.items():
        for name, dtype in (("vertices", "<f4"), ("faces", "<u4")):
            data = base64.b64decode(original["meshes"][int(key)][name])
            expected = np.frombuffer(data, dtype=dtype)
            info = mesh[name]
            actual = np.frombuffer(raw, dtype=dtype if name == "vertices" else f"<u{info['bytes']}",
                                   count=info["count"], offset=start + info["offset"])
            np.testing.assert_array_equal(expected, actual)
    assert len(asset.compressed) < 4_000_000  # Bound the pinned official asset, without decimation.


def test_large_indices_remain_uint32_and_simultaneous_rooms_build_once(monkeypatch, tmp_path):
    calls = []
    model = {"meshes": {"0": {
        "vertices": base64.b64encode(np.zeros(9, dtype="<f4").tobytes()).decode(),
        "faces": base64.b64encode(np.array([0, 65536, 3], dtype="<u4").tobytes()).decode(),
    }}}

    def load(_):
        calls.append(1)
        time.sleep(.02)
        return model

    monkeypatch.setattr(model_assets, "official_preview", load)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assets = list(pool.map(model_assets.visual_asset, [tmp_path] * 4))
    assert len(calls) == 1 and len({asset.version for asset in assets}) == 1
    raw = gzip.decompress(assets[0].compressed)
    size = struct.unpack_from("<I", raw, 4)[0]
    assert json.loads(raw[8:8 + size])["meshes"]["0"]["faces"]["bytes"] == 4


def test_shared_asset_handles_proxy_encoding_and_conditional_requests(monkeypatch):
    with TestClient(create_app()) as client:
        manifest = client.get("/api/models/microduck/manifest")
        assert manifest.status_code == 200
        info = manifest.json()
        assert info["source"] == "official_microduck_visuals" and info["physics"] is False
        assert "model_prepare;dur=" in manifest.headers["server-timing"]
        assert client.get("/api/models/microduck/manifest", headers={
            "If-None-Match": manifest.headers["etag"]}).status_code == 304
        url = f"/api/models/microduck/assets/{info['version']}.dkm.gz"
        response = client.get(url, headers={"Accept-Encoding": "identity"})
        assert response.content.startswith(b"DKM1")
        assert len(response.content) == info["decoded_bytes"]
        assert int(response.headers["content-length"]) == info["encoded_bytes"]
        assert response.headers["content-encoding"] == "gzip"
        assert "immutable" in response.headers["cache-control"]
        cached = client.get(url, headers={"If-None-Match": response.headers["etag"]})
        assert cached.status_code == 304
        assert client.get("/api/models/microduck/assets/invalid.dkm.gz").status_code == 404
        assert client.get(f"/api/models/microduck/assets/{'0' * 64}.dkm.gz").status_code == 404
        assert client.get("/api/scenes/state").status_code == 503  # Visuals never start physics.
        monkeypatch.setenv("DUCKKING_SIM_DIR", "/missing-private-visuals")
        for path in ["/api/models/microduck/manifest", url]:
            failed = client.get(path)
            assert failed.status_code == 503
            assert "setup_scenarios.sh" in failed.text and "private-visuals" not in failed.text


def test_browser_timings_are_bounded_and_never_accept_device_or_url_fields(caplog):
    body = {"result": "ready", "cache": "persistent", "elapsed_ms": 123, "navigation_ms": 456}
    with TestClient(create_app()) as client, caplog.at_level(logging.INFO, logger="uvicorn.error"):
        assert client.post("/api/models/load-metrics?room=2", json=body).status_code == 204
        assert "official_model_load source=browser_reported room=2" in caplog.text
        assert client.post("/api/models/load-metrics", json=body | {
            "view": "scenario", "scene": "rollers", "cache": "memory",
        }).status_code == 204
        assert client.post("/api/models/load-metrics?room=3", json=body).status_code == 404
        for changes in [{"token": "not-a-real-token"}, {"elapsed_ms": -1}, {"cache": "invented"},
                        {"transfer_bytes": 100_000_000}, {"url": "https://invalid.example"},
                        {"scene": "untrusted-free-text"}]:
            assert client.post("/api/models/load-metrics", json=body | changes).status_code == 422
        response = client.post(
            "/api/models/load-metrics", content=json.dumps(body | {"elapsed_ms": float("nan")}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


def test_compressed_scene_geometry_matches_real_world_and_survives_reset():
    with TestClient(create_app()) as client:
        assert client.get("/api/scenes/model.dkm.gz").status_code == 503
        started = client.post("/api/scenes/start", json={"name": "scene_ball"})
        assert started.status_code == 202
        original = client.get("/api/scenes/model").json()
        response = client.get("/api/scenes/model.dkm.gz", headers={"Accept-Encoding": "identity"})
        assert response.status_code == 200 and response.headers["content-encoding"] == "gzip"
        raw = response.content
        assert raw[:4] == b"DKM1"
        size = struct.unpack_from("<I", raw, 4)[0]
        model = json.loads(raw[8:8 + size])
        assert model["physics"] and model["source"] == "official_microduck_physics"
        assert model["revision"] == original["revision"]
        assert model["geoms"] == original["geoms"]
        start = 8 + (size + 3) // 4 * 4
        for key, mesh in model["meshes"].items():
            for name, dtype in (("vertices", "<f4"), ("faces", "<u4")):
                info = mesh[name]
                expected = np.frombuffer(base64.b64decode(original["meshes"][key][name]), dtype)
                actual = np.frombuffer(raw, dtype if name == "vertices" else f"<u{info['bytes']}",
                                       info["count"], start + info["offset"])
                np.testing.assert_array_equal(actual, expected)
        # A reset changes state, not the exported geometry or model revision.
        client.post("/api/scenes/actions", json={"name": "reset"})
        assert client.get("/api/scenes/model.dkm.gz").content == raw
