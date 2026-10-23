import asyncio
import json
import tempfile
import time
from pathlib import Path

import pytest

from duckking.robotd import RobotdBackend


@pytest.fixture
def socket_dir():
    # macOS limits sockaddr_un paths to ~104 bytes; pytest tmp paths can exceed that.
    with tempfile.TemporaryDirectory(prefix="dk-", dir="/tmp") as directory:
        yield Path(directory)


async def test_real_unix_socket_notifications_state_and_discrete_requests(socket_dir):
    path = socket_dir / "robot.sock"
    received = []

    async def daemon(reader, writer):
        try:
            while line := await reader.readline():
                request = json.loads(line)
                received.append(request)
                if request["method"] == "robot.subscribe":
                    writer.write(
                        (
                            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"accepted": True}})
                            + "\n"
                        ).encode()
                    )
                    writer.write(
                        (
                            json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "method": "robot.state",
                                    "params": {"policy": "stand", "head": [0.3, 0.3, 0, 0]},
                                }
                            )
                            + "\n"
                        ).encode()
                    )
                elif "id" in request:
                    writer.write(
                        (
                            json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "id": request["id"],
                                    "result": {"accepted": True},
                                }
                            )
                            + "\n"
                        ).encode()
                    )
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(daemon, path)
    backend = RobotdBackend(str(path))
    async with server:
        await backend.snapshot()
        async with asyncio.timeout(2):
            while not (await backend.snapshot())["connected"]:  # noqa: ASYNC110 - black-box socket polling
                await asyncio.sleep(0.01)
        await backend.move(0.1, 0)
        await backend.move(0, 0.2, -0.28)
        await backend.head(0.1, 0.2, 0.05)
        await backend.body_pose(-0.01, 0.05, 0.02, True)
        await backend.stop()
        assert not backend.pose_active
        assert backend.neutral_head is None
        with pytest.raises(ValueError):
            await backend.reset()
        await asyncio.sleep(0.01)
        assert any(r["method"] == "robot.move" and "id" not in r for r in received)
        assert any(r.get("params", {}).get("vy") == -0.28 for r in received)
        assert any(r["method"] == "robot.pose" and r["params"]["active"] is False for r in received)
        assert (await backend.snapshot())["telemetry"]["policy"] == "stand"
        backend.received -= 2
        with pytest.raises(OSError):
            await backend.move(0.1, 0)
        with pytest.raises(OSError):
            await backend.head(0.1)
        await backend.close()
    await asyncio.sleep(0.01)


@pytest.mark.parametrize(
    "response",
    [
        {"id": 99, "result": {}},
        {"id": 1, "error": {"code": -1}},
        {"id": 1, "result": {"accepted": False, "reason": "disabled"}},
    ],
)
async def test_rpc_rejection_cannot_be_reported_as_success(socket_dir, response):
    path = socket_dir / "robot.sock"

    async def daemon(reader, writer):
        await reader.readline()
        writer.write((json.dumps(response) + "\n").encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(daemon, path)
    async with server:
        with pytest.raises(OSError):
            await RobotdBackend(str(path)).stop()


async def test_missing_socket_stays_disconnected_without_preview_fallback(socket_dir):
    backend = RobotdBackend(str(socket_dir / "missing.sock"))
    state = await backend.snapshot()
    assert state["kind"] == "robotd"
    assert not state["connected"]
    await asyncio.sleep(0.01)
    assert "未连接" in backend.error
    await backend.close()


@pytest.mark.parametrize("message", [None, {"error": {"code": -1}}, "invalid-json"])
async def test_state_disconnect_and_subscription_rejections(socket_dir, message):
    path = socket_dir / "robot.sock"

    async def daemon(reader, writer):
        await reader.readline()
        if message is not None:
            writer.write(
                ((message if isinstance(message, str) else json.dumps(message)) + "\n").encode()
            )
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(daemon, path)
    async with server:
        backend = RobotdBackend(str(path))
        await backend._subscribe()
        assert backend.error
        await backend.close()


async def test_failed_notification_discards_broken_writer(socket_dir):
    class BrokenWriter:
        def is_closing(self):
            return False

        def write(self, data):
            pass

        async def drain(self):
            raise OSError("broken")

        def close(self):
            pass

    backend = RobotdBackend(str(socket_dir / "unused"))
    backend.writer = BrokenWriter()
    with pytest.raises(OSError):
        await backend._notify("robot.move", {})
    assert backend.writer is None


@pytest.mark.parametrize("head", [None, [], [0, 0, 0, float("nan")]])
async def test_nod_requires_a_known_finite_head_baseline(socket_dir, head):
    backend = RobotdBackend(str(socket_dir / "unused"))
    backend.received = time.monotonic()
    backend.state = {"head": head}
    with pytest.raises(ValueError):
        await backend.head(0.1)


@pytest.mark.parametrize("flag", ["fallen", "limp", "picked_up"])
async def test_body_and_head_commands_refuse_unsafe_reported_state(socket_dir, flag):
    backend = RobotdBackend(str(socket_dir / "unused"))
    backend.received = time.monotonic()
    backend.state = {"safety": {flag: True}}
    with pytest.raises(OSError, match="姿态"):
        await backend.body_pose(-0.01, 0, 0, True)


@pytest.mark.parametrize(
    "values", [(-0.1, 0, 0), (0.02, 0, 0), (0, 0.3, 0), (0, 0, 0.3), (float("nan"), 0, 0)]
)
async def test_body_pose_never_sends_out_of_training_range(socket_dir, values):
    backend = RobotdBackend(str(socket_dir / "unused"))
    backend.received = time.monotonic()
    with pytest.raises(ValueError):
        await backend.body_pose(*values, True)


@pytest.mark.parametrize("failed_method", [None, "robot.pose", "robot.head"])
@pytest.mark.parametrize("ack_error", [OSError, ValueError])
async def test_stop_attempts_all_restores_even_when_stop_ack_fails(
    socket_dir, failed_method, ack_error
):
    backend = RobotdBackend(str(socket_dir / "unused"))
    backend.neutral_head = [0.1, 0.2, 0.3, 0.04]
    backend.pose_active = True
    attempts = []

    async def failed_rpc(*args):
        raise ack_error("no stop ack")

    async def notify(method, params):
        attempts.append((method, params))
        if method == failed_method:
            raise OSError("restore unavailable")

    backend._rpc, backend._notify = failed_rpc, notify
    with pytest.raises(OSError, match="no stop ack"):
        await backend.stop()
    assert [method for method, _ in attempts] == ["robot.pose", "robot.head"]
    assert attempts[0][1]["active"] is False
    assert attempts[1][1]["head_yaw"] == 0.3
    assert backend.pose_active == (failed_method == "robot.pose")
    assert (backend.neutral_head is not None) == (failed_method == "robot.head")


async def test_head_offsets_are_clamped_and_neutral_pose_is_preserved(socket_dir):
    backend = RobotdBackend(str(socket_dir / "unused"))
    backend.received = time.monotonic()
    backend.state = {"head": [0.1, 1.05, 1.35, 0.29]}
    sent = []

    async def notify(method, params):
        sent.append(params)

    backend._notify = notify
    await backend.head(0.2, 0.2, 0.2)
    assert sent[-1] == {"neck_pitch": 0.1, "head_pitch": 1.1, "head_yaw": 1.4, "head_roll": 0.31}
    await backend.head(-5, -5, -5)
    assert sent[-1]["head_yaw"] == -1.4 and sent[-1]["head_roll"] == -0.31
    assert backend.neutral_head == [0.1, 1.05, 1.35, 0.29]
