import asyncio
import json
import tempfile
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
        await backend.head(0.1)
        await backend.stop()
        with pytest.raises(ValueError):
            await backend.reset()
        await asyncio.sleep(0.01)
        assert any(r["method"] == "robot.move" and "id" not in r for r in received)
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
