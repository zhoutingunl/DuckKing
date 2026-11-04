from fastapi.testclient import TestClient

from duckking.app import create_app
from duckking.config import Settings
from duckking.statistics import VoiceStatistics, distribution


def feed(stats, event, elapsed=0, turn=1, backend="preview", **fields):
    stats.observe({
        "event": event, "turn": turn, "backend": backend, "elapsed_ms": elapsed,
        "time": "2026-10-23T15:00:00+00:00", **fields,
    }, elapsed / 1000)


def test_latency_denominators_failures_pending_and_nearest_rank():
    stats = VoiceStatistics()
    feed(stats, "listen_start")
    feed(stats, "listen_stop", 1000, uplink_frames=10)
    feed(stats, "stt", 1300, text="前进左转右转")
    feed(stats, "stt", 1500, text="前进，左转，右转")
    feed(stats, "action_start", 1700, call=1, tool="duck_walk_short")
    feed(stats, "action_start", 1800, call=2, tool="duck_stop")
    feed(stats, "action_end", 1850, call=2, result="completed")
    feed(stats, "action_end", 1900, call=1, result="cancelled")
    feed(stats, "action_end", 2000, call=1, result="completed")  # Cannot overwrite cancellation.
    feed(stats, "downlink_first_frame", 2300, downlink_frames=1)
    feed(stats, "tts_stop", 4000, result="ok", downlink_frames=20)
    feed(stats, "state", 5000, state="disconnected")  # No false interruption of a finished turn.
    feed(stats, "listen_start", turn=2)
    feed(stats, "listen_stop", 1000, turn=2)
    feed(stats, "timeout", 21000, turn=2, reason="response_idle")
    feed(stats, "tts_stop", 22000, turn=2, result="ok")  # Late stop cannot turn timeout to success.
    feed(stats, "listen_start", turn=3)
    feed(stats, "listen_stop", 1000, turn=3)
    result = stats.snapshot()
    assert result["counts"] == {
        "rounds": 3, "submitted": 3, "closed": 2, "cloud_closed": 2, "pending": 1,
        "recognized": 1, "replied": 1,
        "timeouts": 1, "interrupted": 0, "errors": 0, "actions": 2, "finished_actions": 2,
        "completed_actions": 1,
    }
    assert result["latencies"]["stt"] == {
        "count": 1, "mean_ms": 300.0, "p50_ms": 300, "p90_ms": 300, "p95_ms": 300
    }
    assert result["latencies"]["action_start"]["p50_ms"] == 700
    assert result["latencies"]["first_audio"]["p50_ms"] == 1300
    assert result["latencies"]["reply_end"]["p50_ms"] == 3000
    assert result["latencies"]["action_duration"] == {
        "count": 2, "mean_ms": 125.0, "p50_ms": 50, "p90_ms": 200, "p95_ms": 200
    }
    assert result["rounds"][-1]["downlink_frames"] == 20
    assert distribution(list(range(1, 21))) == {
        "count": 20, "mean_ms": 10.5, "p50_ms": 10, "p90_ms": 18, "p95_ms": 19
    }


def test_backend_isolation_bounded_samples_recovery_and_missing_observations():
    stats = VoiceStatistics(capacity=2)
    feed(stats, "tts_stop", result="ok")  # Cloud greeting is not a round.
    feed(stats, "state", state="recovering")
    feed(stats, "state", 250, state="ready")
    feed(stats, "state", 500, state="ready")  # No duplicate recovery.
    feed(stats, "state", 600, backend="robotd", state="recovering")
    feed(stats, "connection_error", 700, backend="robotd")
    feed(stats, "state", 700, backend="robotd", state="error")
    feed(stats, "state", 800, backend="robotd", state="ready")
    feed(stats, "listen_start", turn=1)
    feed(stats, "reset", turn=1, reason="manual")  # Recording wasn't submitted.
    feed(stats, "listen_start", turn=2, backend="robotd")
    feed(stats, "stt", 100, turn=2, backend="robotd", text="左转")
    feed(stats, "timeout", 150, turn=2, backend="robotd", reason="recording_limit")
    feed(stats, "listen_stop", 200, turn=2, backend="robotd")
    feed(stats, "action_end", 250, turn=2, backend="robotd", call=999, result="completed")
    feed(stats, "tts_stop", 300, turn=2, backend="robotd", result="aborted")
    feed(stats, "listen_start", turn=3)
    feed(stats, "listen_stop", 200, turn=3)
    feed(stats, "command_error", 300, turn=3)
    feed(stats, "state", backend="invalid", state="ready")
    result = stats.snapshot("robotd")
    assert result["counts"]["rounds"] == 1
    assert result["counts"]["recognized"] == 1
    assert result["counts"]["interrupted"] == 1
    assert result["counts"]["timeouts"] == 0
    assert result["latencies"]["stt"]["count"] == 0  # STT before stop, not a negative latency.
    assert result["latencies"]["action_start"]["p50_ms"] is None
    assert result["service"] == {"reconnect_attempts": 1, "connection_error": 1, "timeout": 1}
    assert stats.snapshot()["latencies"]["recovery"]["p50_ms"] == 250
    assert stats.snapshot()["total_rounds"] == 3 and len(stats.rounds) == 2
    assert stats.snapshot("preview")["counts"]["errors"] == 1


def test_disconnect_of_unsubmitted_recording_and_empty_stt():
    stats = VoiceStatistics()
    feed(stats, "listen_start")
    feed(stats, "stt", text="  ")
    feed(stats, "state", state="disconnected")
    result = stats.snapshot()
    assert result["counts"]["interrupted"] == 1
    assert result["counts"]["closed"] == result["counts"]["recognized"] == 0
    assert result["latencies"]["stt"]["count"] == 0


def test_statistics_api_same_origin_filter_empty_and_no_store(tmp_path):
    app = create_app(settings=Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        response = client.get("/api/voice/statistics")
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["counts"]["rounds"] == 0
        journal = app.state.voice_diagnostics
        turn = journal.next_turn()
        journal.record("listen_start", turn=turn, backend="preview")
        journal.record("stt", turn=turn, backend="preview", text="左转 token=secret")
        payload = client.get("/api/voice/statistics?backend=preview").json()
        assert "secret" not in str(payload)
        assert payload["rounds"][0]["text"].startswith("左转")
        assert client.get("/api/voice/statistics?backend=robotd").json()["rounds"] == []
        assert client.get("/api/voice/statistics?backend=unknown").status_code == 422
        assert client.get(
            "/api/voice/statistics", headers={"origin": "https://external.example"}
        ).status_code == 403


def test_physics_posture_rounds_reach_statistics_and_stay_room_scoped(tmp_path):
    app = create_app(settings=Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        journal = app.state.rooms["2"].voice_diagnostics
        fields = {"turn": journal.next_turn(), "backend": "mujoco"}
        journal.record("listen_start", **fields, elapsed_ms=0)
        journal.record("listen_stop", **fields, elapsed_ms=1000)
        journal.record("stt", **fields, elapsed_ms=1200, text="坐下再站起来 token=secret")
        for call, tool in enumerate(("duck_sit", "duck_stand"), 1):
            journal.record("action_start", **fields, elapsed_ms=call * 2000, call=call, tool=tool)
            journal.record("action_end", **fields, elapsed_ms=call * 2000 + 700,
                           call=call, result="completed")
        journal.record("tts_stop", **fields, elapsed_ms=6000, result="ok")
        response = client.get("/api/voice/statistics?room=2&backend=mujoco")
        assert response.status_code == 200
        result = response.json()
        assert result["counts"]["replied"] == 1
        assert result["counts"]["completed_actions"] == 2
        assert [a["tool"] for a in result["rounds"][0]["actions"]] == ["duck_sit", "duck_stand"]
        assert result["latencies"]["action_duration"]["p95_ms"] == 700
        assert "secret" not in response.text
        assert client.get("/api/voice/statistics?room=2&backend=preview").json()["rounds"] == []
        assert client.get("/api/voice/statistics?room=1").json()["rounds"] == []


def test_recognition_engine_timings_do_not_mix_fallback_local_and_cloud():
    stats = VoiceStatistics()
    feed(stats, "listen_start", mode="local_first")
    feed(stats, "listen_stop", 1000)
    feed(stats, "stt", 1200, source="local", text="未匹配的问题")
    feed(stats, "voice_route", 1205, route="cloud_fallback", reason="unmatched")
    feed(stats, "stt", 1800, text="云端识别的问题")
    feed(stats, "stt", 1900, text="云端修订的问题")
    feed(stats, "tts_stop", 2200, result="ok")
    feed(stats, "listen_start", turn=2)
    feed(stats, "stt", 500, turn=2, text="录音结束前返回")
    feed(stats, "listen_stop", 1000, turn=2)
    feed(stats, "listen_start", turn=3, backend="mujoco", mode="local_first")
    feed(stats, "listen_stop", 1000, turn=3, backend="mujoco")
    feed(stats, "stt", 1400, turn=3, backend="mujoco", source="local", text="点头")
    result = stats.snapshot()["routing"]["recognition_latency"]
    assert result["local"] == {
        "count": 2, "mean_ms": 300.0, "p50_ms": 200, "p90_ms": 400, "p95_ms": 400
    }
    assert result["cloud"] == {
        "count": 1, "mean_ms": 800.0, "p50_ms": 800, "p90_ms": 800, "p95_ms": 800
    }
    assert stats.snapshot("mujoco")["routing"]["recognition_latency"]["cloud"]["count"] == 0
    assert all(value is None for key, value in distribution([]).items() if key != "count")
