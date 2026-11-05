"""Measure isolated real-server physics with bounded scenes, sockets and cleanup.
Run only against a dedicated loopback benchmark instance, never a shared live room.
"""

import argparse
import asyncio
import json
import math
import os
import time
from pathlib import Path

import httpx
import websockets


def stats(a):
    a = sorted(a)
    return (
        {
            "n": len(a),
            "min": round(a[0], 3),
            "mean": round(sum(a) / len(a), 3),
            "p50": round(a[math.ceil(len(a) * 0.5) - 1], 3),
            "p95": round(a[math.ceil(len(a) * 0.95) - 1], 3),
            "p99": round(a[math.ceil(len(a) * 0.99) - 1], 3),
            "max": round(a[-1], 3),
        }
        if a
        else {"n": 0}
    )


def emit(row, path):
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **row}
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row), flush=True)


def physics_state(packet):
    state = packet.get("backend", packet)
    if not isinstance(state, dict) or "sim_time" not in state:
        raise ValueError("Missing actual physics time in state payload")
    return state


def stage_passed(count, readings, actions, health):
    rtfs = [r["active_rtf"] for r in readings if r.get("active_rtf") is not None]
    return (
        len(rtfs) == count
        and min(rtfs) >= 0.90
        and health["health_errors"] == 0
        and health["health_ms"].get("p95", 99999) < 500
        and all(r.get("frame_gap_ms", {}).get("p95", 99999) < 150 for r in readings)
        and not any(r.get("error") for r in readings)
        and len(actions) == count
        and all(r.get("status") in {"completed", "accepted"} for r in actions)
    )


async def main(args):
    assert args.url.startswith("http://127.0.0.1:18765"), "Dedicated instance required"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url=args.url, timeout=90, trust_env=False) as client:

        async def req(path, method="GET", **kw):
            r = await client.request(method, path, **kw)
            r.raise_for_status()
            return r.json() if r.content else None

        async def action(room, name, wait=True):
            r = await req(f"/api/scenes/actions?room={room}", "POST", json={"name": name})
            return await wait_action(room, r["id"]) if wait else r

        async def wait_action(room, ident):
            async with asyncio.timeout(90):
                while True:
                    r = await req(f"/api/scenes/actions/{ident}?room={room}")
                    if r["status"] != "running":
                        return r
                    await asyncio.sleep(0.1)

        rooms = await req("/api/rooms")
        assert not any(r["viewers"] or r["voice_busy"] or r["physics"] for r in rooms["rooms"])
        for _ in range(max(args.counts) - len(rooms["rooms"])):
            await req("/api/rooms", "POST")
        emit(
            {
                "phase": "start",
                "release": (await req("/api/health"))["release"],
                "quota_label": args.label,
                "counts": args.counts,
                "duration": args.duration,
            },
            args.output,
        )
        for scene in args.scenes:
            for count in args.counts:
                selected = [str(i) for i in range(1, count + 1)]
                existing = {r["id"] for r in (await req("/api/rooms"))["rooms"]}
                while not set(selected).issubset(existing):
                    existing.add((await req("/api/rooms", "POST"))["room"])
                started = time.monotonic()
                initialized = []
                tasks = []
                watchers = []
                monitor_task = None
                stop = None
                finishes = []

                async def prepare(room, scene=scene, initialized=initialized):
                    initialized.append(room)
                    if scene in {"balance", "seesaw"}:
                        await req(f"/api/{scene}/prepare?room={room}", "POST")
                    else:
                        a = await req(
                            f"/api/scenes/start?room={room}",
                            "POST",
                            json={"name": "scene_" + scene},
                        )
                        a = await wait_action(room, a["id"])
                        if a["status"] != "completed":
                            raise RuntimeError("scene_prepare_failed")

                try:
                    for room in selected:
                        await prepare(room)
                    preparation = time.monotonic() - started

                    async def exercise(room, scene=scene):
                        if scene == "table":
                            a = await action(room, "table_show")
                            return {
                                "room": room,
                                "status": a["status"],
                                "verified": a.get("outcome", {}).get("verified"),
                                "error": a.get("error"),
                            }
                        if scene == "balance":
                            await req(
                                f"/api/balance/command?room={room}",
                                "POST",
                                json={
                                    "operation": "start",
                                    "level": 1,
                                    "seed": 42,
                                    "controller": "trained",
                                    "compare": True,
                                    "duration_seconds": 33,
                                },
                            )
                        elif scene == "seesaw":
                            await req(
                                f"/api/seesaw/command?room={room}",
                                "POST",
                                json={
                                    "operation": "start",
                                    "controller": "trained",
                                    "mode": "compare",
                                },
                            )
                        else:
                            for _ in range(5):
                                a = await action(room, "nod")
                                if a["status"] != "completed":
                                    return {"room": room, "status": a["status"]}
                                await asyncio.sleep(2)
                        return {
                            "room": room,
                            "status": "accepted" if scene in {"balance", "seesaw"} else "completed",
                        }

                    stop = asyncio.Event()
                    start_gate = asyncio.Event()
                    watchers_ready = 0

                    async def watch(room, scene=scene, stop=stop, start_gate=start_gate):
                        nonlocal watchers_ready
                        gaps = []
                        times = []
                        last = None
                        frames = 0
                        last_state = {}
                        begin_state = None
                        cookie = client.build_request('GET', '/api/rooms').headers.get('cookie')
                        async with websockets.connect(
                            args.url.replace("http:", "ws:") + f"/scene-ws?room={room}",
                            origin=args.url,
                            max_size=16 * 1024 * 1024,
                            proxy=None,
                            additional_headers={'Cookie': cookie} if cookie else None,
                        ) as ws:
                            watchers_ready += 1
                            await start_gate.wait()
                            while not stop.is_set():
                                packet = json.loads(await asyncio.wait_for(ws.recv(), 5))
                                now = time.monotonic()
                                state = packet.get("backend", packet)
                                if not isinstance(state, dict) or "sim_time" not in state:
                                    raise RuntimeError(
                                        "Missing actual physics time in state payload"
                                    )
                                if last is not None:
                                    gaps.append((now - last) * 1000)
                                last = now
                                frames += 1
                                last_state = state
                                phase = state.get("balance", state.get("seesaw", {})).get("phase")
                                if scene in {"balance", "seesaw"}:
                                    # Sample advancing physics; exclude paused results.
                                    sim = (
                                        state.get("balance", {})
                                        .get("comparison", {})
                                        .get("physics_time", state.get("sim_time", 0))
                                    )
                                    if phase in {"running", "stopping", "settling"} and sim > 0:
                                        times.append((now, sim))
                                else:
                                    times.append((now, state.get("sim_time", 0)))
                                if begin_state is None:
                                    begin_state = state
                                await ws.send("next")
                        rtf = (
                            (times[-1][1] - times[0][1]) / (times[-1][0] - times[0][0])
                            if len(times) > 2 and times[-1][0] > times[0][0]
                            else None
                        )
                        return {
                            "room": room,
                            "frames": frames,
                            "frame_gap_ms": stats(gaps),
                            "active_rtf": round(rtf, 4) if rtf is not None else None,
                            "active_observation_s": round(times[-1][0] - times[0][0], 3)
                            if len(times) > 1
                            else 0,
                            "server_rtf": last_state.get("real_time_factor"),
                            "error": last_state.get("error"),
                            "phase": last_state.get("balance", last_state.get("seesaw", {})).get(
                                "phase"
                            ),
                        }

                    watchers = [asyncio.create_task(watch(r)) for r in selected]

                    async def monitor(stop=stop):
                        health = []
                        failures = 0
                        rss = []
                        cpu = []
                        last_ticks = None
                        last_time = None
                        while not stop.is_set():
                            t = time.monotonic()
                            try:
                                await req("/api/health", timeout=3)
                                health.append((time.monotonic() - t) * 1000)
                            except Exception:
                                failures += 1
                            try:
                                values = (
                                    (
                                        await asyncio.to_thread(
                                            Path(f"/proc/{args.pid}/stat").read_text
                                        )
                                    )
                                    .split(") ", 1)[1]
                                    .split()
                                )
                                ticks = int(values[11]) + int(values[12])
                                now = time.monotonic()
                                if last_ticks is not None:
                                    cpu.append(
                                        (ticks - last_ticks)
                                        / os.sysconf("SC_CLK_TCK")
                                        / (now - last_time)
                                        * 100
                                    )
                                last_ticks, last_time = ticks, now
                                rss.append(int(values[21]) * os.sysconf("SC_PAGE_SIZE") / 1024**2)
                            except (OSError, ValueError):
                                pass
                            await asyncio.sleep(0.5)
                        return {
                            "health_ms": stats(health),
                            "health_errors": failures,
                            "rss_mib": stats(rss),
                            "process_cpu_percent": stats(cpu),
                        }

                    monitor_task = asyncio.create_task(monitor())
                    while watchers_ready < count:
                        if any(w.done() for w in watchers):
                            raise RuntimeError("watcher_failed_before_start")
                        await asyncio.sleep(0.02)
                    start_gate.set()
                    tasks = [asyncio.create_task(exercise(r)) for r in selected]
                    await asyncio.sleep(args.duration)
                    stop.set()
                    readings = await asyncio.gather(*watchers, return_exceptions=True)
                    health = await monitor_task
                    for t in tasks:
                        if not t.done():
                            t.cancel()
                    raw = await asyncio.gather(*tasks, return_exceptions=True)
                    finishes = [
                        r if isinstance(r, dict) else {"status": type(r).__name__} for r in raw
                    ]
                    readings = [
                        r if isinstance(r, dict) else {"error": type(r).__name__} for r in readings
                    ]
                    passed = stage_passed(count, readings, finishes, health)
                    emit(
                        {
                            "phase": "physics",
                            "scene": scene,
                            "rooms": count,
                            "quota_label": args.label,
                            "prepare_s": round(preparation, 3),
                            "smooth_criteria_passed": passed,
                            "readings": readings,
                            "actions": finishes,
                            **health,
                        },
                        args.output,
                    )
                    if not passed:
                        break
                except Exception as exc:
                    emit(
                        {
                            "phase": "physics_error",
                            "scene": scene,
                            "rooms": count,
                            "error": type(exc).__name__,
                            "message": str(exc)[:160],
                        },
                        args.output,
                    )
                    break
                finally:
                    if stop is not None:
                        stop.set()
                    background = [*watchers, *([monitor_task] if monitor_task else [])]
                    for task in background:
                        if not task.done():
                            task.cancel()
                    if background:
                        await asyncio.gather(*background, return_exceptions=True)
                    for t in tasks:
                        t.cancel()
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                    for room in initialized:
                        try:
                            await req(f"/api/scenes/close?room={room}", "POST", timeout=30)
                        except Exception:
                            pass
                    await asyncio.sleep(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://127.0.0.1:18765")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument(
        "--scenes",
        nargs="+",
        choices=["skills", "table", "balance", "seesaw"],
        default=["skills", "table", "balance", "seesaw"],
    )
    ap.add_argument("--counts", nargs="+", type=int, default=[1, 2, 4, 6, 8])
    ap.add_argument("--duration", type=int, default=45)
    args = ap.parse_args()
    if not all(1 <= n <= 16 for n in args.counts) or not 15 <= args.duration <= 90:
        ap.error("Bound exceeded")
    asyncio.run(main(args))
