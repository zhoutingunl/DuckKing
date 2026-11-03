"""Explicit bounded live mixed-load acceptance; uses only newly claimed idle rooms."""

import argparse
import asyncio
import json
import time
from pathlib import Path

from benchmark_audience import Probe, emit, stats


async def main(args):
    probe = Probe(args.url, args.output)
    owned, watchers, action_tasks = [], [], []
    stop, measure = asyncio.Event(), asyncio.Event()
    try:
        before = (await probe.request("api/rooms")).json()
        if before["physics_active"] + len(args.scenes) > before["physics_capacity"]:
            raise RuntimeError("Not enough unused physical slots; preserve existing users")
        emit(
            {
                "phase": "mixed_start",
                "rooms_before": before,
                "scenes": args.scenes,
                "cloud_clients": args.cloud,
                "state_clients": args.viewers,
                "duration_s": args.duration,
            },
            args.output,
        )

        async def request(path, method="GET", **kwargs):
            r = await probe.request(path, method, **kwargs)
            return r.json() if r.content else None

        async def wait_action(room, ident):
            async with asyncio.timeout(100):
                while True:
                    a = await request(f"api/scenes/actions/{ident}?room={room}")
                    if a["status"] != "running":
                        return {
                            "room": room,
                            "status": a["status"],
                            "verified": a.get("outcome", {}).get("verified"),
                            "error": a.get("error"),
                        }
                    await asyncio.sleep(0.2)

        async def watch(room, ws):
            readings, gaps = [], []
            last = None
            while not stop.is_set():
                packet = json.loads(await asyncio.wait_for(ws.recv(), 5))
                now = time.monotonic()
                state = packet.get("backend", {})
                if measure.is_set() and "sim_time" in state:
                    readings.append((now, state["sim_time"]))
                    if last is not None:
                        gaps.append((now - last) * 1000)
                    last = now
                await ws.send("next")
            await ws.close()
            return {
                "room": room,
                "samples": len(readings),
                "frame_gap_ms": stats(gaps),
                "rtf": round(
                    (readings[-1][1] - readings[0][1]) / (readings[-1][0] - readings[0][0]), 4
                )
                if len(readings) > 1
                else None,
            }

        for scene in args.scenes:
            room = await probe.claim()
            ws = await probe.socket("scene-ws", room)
            owned.append((room, scene, ws))
            watchers.append(asyncio.create_task(watch(room, ws)))
            action = await request(
                f"api/scenes/start?room={room}", "POST", json={"name": "scene_" + scene}
            )
            result = await wait_action(room, action["id"])
            if result["status"] != "completed":
                raise RuntimeError("Physical scene did not prepare")
        measure.set()

        async def exercise(room, scene):
            result = None
            for _ in range(1 if scene == "table" else 10):
                action = await request(
                    f"api/scenes/actions?room={room}",
                    "POST",
                    json={"name": "table_show" if scene == "table" else "nod"},
                )
                result = await wait_action(room, action["id"])
                if result["status"] != "completed":
                    break
                await asyncio.sleep(2)
            return result

        action_tasks = [asyncio.create_task(exercise(r, s)) for r, s, _ in owned]
        cloud = asyncio.create_task(probe.cloud(args.cloud, args.wav, 3))
        audience = asyncio.create_task(probe.public([args.viewers], args.duration, 0))
        workloads = [cloud, audience]
        try:
            await asyncio.wait_for(asyncio.gather(*workloads), timeout=args.duration + 120)
        finally:
            for task in workloads:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*workloads, return_exceptions=True)
        stop.set()
        readings = await asyncio.gather(*watchers, return_exceptions=True)
        actions = await asyncio.gather(*action_tasks, return_exceptions=True)
        emit(
            {
                "phase": "mixed_physics",
                "readings": [
                    r if isinstance(r, dict) else {"error": type(r).__name__} for r in readings
                ],
                "actions": [
                    r if isinstance(r, dict) else {"error": type(r).__name__} for r in actions
                ],
            },
            args.output,
        )
    finally:
        stop.set()
        for task in [*watchers, *action_tasks]:
            if not task.done():
                task.cancel()
        if watchers or action_tasks:
            await asyncio.gather(*watchers, *action_tasks, return_exceptions=True)
        for room, _, ws in owned:
            await ws.close()
            await probe.request(f"api/scenes/close?room={room}", "POST")
        await probe.client.aclose()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument(
        "--scenes", nargs="+", choices=["skills", "table"], default=["skills", "skills", "table"]
    )
    ap.add_argument("--cloud", type=int, default=20)
    ap.add_argument("--viewers", type=int, default=100)
    ap.add_argument("--duration", type=int, default=75)
    ap.add_argument(
        "--wav", type=Path, default=Path("frontend/public/demo-audio/interview-command.wav")
    )
    args = ap.parse_args()
    if not (
        1 <= len(args.scenes) <= 4
        and 1 <= args.cloud <= 24
        and 1 <= args.viewers <= 100
        and 30 <= args.duration <= 120
    ):
        ap.error("Bounded workload exceeded")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(main(args))
