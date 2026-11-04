"""Bounded live audience probes; cloud mode consumes real configured Linx sessions.

Only claim idle rooms. Never change bindings, replay failed speech, or count a
handshake as successful voice inference. Output contains timings, not identities.
"""

import argparse
import asyncio
import base64
import json
import math
import re
import time
import uuid
import wave
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
import websockets


def stats(values):
    a = sorted(values)
    if not a:
        return {"n": 0}
    return {
        "n": len(a),
        "min": round(a[0], 3),
        "mean": round(sum(a) / len(a), 3),
        **{f"p{p}": round(a[math.ceil(len(a) * p / 100) - 1], 3) for p in [50, 95, 99]},
        "max": round(a[-1], 3),
    }


def emit(value, output):
    value = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **value}
    with output.open("a") as f:
        f.write(json.dumps(value, ensure_ascii=False) + "\n")
    print(json.dumps(value, ensure_ascii=False), flush=True)


class Probe:
    def __init__(self, base, output):
        self.base = base.rstrip("/") + "/"
        u = urlsplit(base)
        self.origin = f"{u.scheme}://{u.netloc}"
        self.wsbase = (
            ("wss" if u.scheme == "https" else "ws") + "://" + u.netloc + u.path.rstrip("/") + "/"
        )
        self.output = output
        self.client = httpx.AsyncClient(
            timeout=45,
            trust_env=False,
            limits=httpx.Limits(max_connections=150, max_keepalive_connections=120),
            headers={"Origin": self.origin},
        )

    async def request(self, path, method="GET", **kwargs):
        r = await self.client.request(method, urljoin(self.base, path), **kwargs)
        r.raise_for_status()
        return r

    async def claim(self):
        return (await self.request("api/rooms/claim", "POST")).json()["room"]

    async def socket(self, endpoint, room):
        return await websockets.connect(
            self.wsbase + endpoint + "?room=" + room,
            origin=self.origin,
            open_timeout=20,
            max_size=8 * 1024 * 1024,
            proxy=None,
        )

    async def health(self, stop):
        times, errors = [], 0
        while not stop.is_set():
            began = time.monotonic()
            try:
                await self.request("api/health", timeout=3)
                times.append((time.monotonic() - began) * 1000)
            except Exception:
                errors += 1
            try:
                await asyncio.wait_for(stop.wait(), 0.5)
            except TimeoutError:
                pass
        return {"latency_ms": stats(times), "errors": errors}

    async def public(self, counts, duration, cold):
        room = await self.claim()
        for n in counts:
            stop = asyncio.Event()
            monitor = asyncio.create_task(self.health(stop))

            async def watch():
                began = time.monotonic()
                gaps = []
                first = None
                frames = 0
                size = 0
                try:
                    async with await self.socket("ws", room) as ws:
                        first = (time.monotonic() - began) * 1000
                        until = time.monotonic() + duration
                        last = None
                        while time.monotonic() < until:
                            msg = await asyncio.wait_for(ws.recv(), 4)
                            now = time.monotonic()
                            if last is not None:
                                gaps.append((now - last) * 1000)
                            last = now
                            frames += 1
                            size += len(msg)
                    return {
                        "ok": True,
                        "connect_ms": first,
                        "gaps": gaps,
                        "frames": frames,
                        "bytes": size,
                    }
                except Exception as e:
                    return {
                        "ok": False,
                        "error": type(e).__name__,
                        "connect_ms": first,
                        "gaps": gaps,
                        "frames": frames,
                        "bytes": size,
                    }

            rows = await asyncio.gather(*(watch() for _ in range(n)))
            stop.set()
            health = await monitor
            result = {
                "phase": "public_state",
                "clients": n,
                "duration_s": duration,
                "successful_clients": sum(r["ok"] for r in rows),
                "connect_ms": stats([r["connect_ms"] for r in rows if r["connect_ms"] is not None]),
                "frame_gap_ms": stats([g for r in rows for g in r["gaps"]]),
                "frames": sum(r["frames"] for r in rows),
                "payload_bytes": sum(r["bytes"] for r in rows),
                "errors": [r["error"] for r in rows if not r["ok"]],
                "health": health,
                "scope": "protocol clients sharing a preview room; no independent rendering",
            }
            emit(result, self.output)
            if result["successful_clients"] < n or health["errors"]:
                break
        if cold:
            home = await self.request("")
            paths = list(
                dict.fromkeys(re.findall(r'(?:src|href)="([^\"]+\.(?:js|css))"', home.text))
            )
            manifest = (await self.request("api/models/microduck/manifest")).json()
            paths += [
                "api/models/microduck/manifest",
                f"api/models/microduck/assets/{manifest['version']}.dkm.gz",
            ]
            paths = [""] + paths

            async def load():
                began = time.monotonic()
                size = 0
                try:
                    for path in paths:
                        async with self.client.stream(
                            "GET", urljoin(self.base, path), timeout=60
                        ) as r:
                            r.raise_for_status()
                            async for chunk in r.aiter_raw():
                                size += len(chunk)
                    return {"ok": True, "ms": (time.monotonic() - began) * 1000, "bytes": size}
                except Exception as e:
                    return {
                        "ok": False,
                        "ms": (time.monotonic() - began) * 1000,
                        "bytes": size,
                        "error": type(e).__name__,
                        "failed_path": path,
                        "detail": str(e)[:240],
                    }

            stop = asyncio.Event()
            monitor = asyncio.create_task(self.health(stop))
            began = time.monotonic()
            cpu_start = time.process_time()
            rows = await asyncio.gather(*(load() for _ in range(cold)))
            stop.set()
            health = await monitor
            emit(
                {
                    "phase": "cold_download",
                    "clients": cold,
                    "paths_per_client": len(paths),
                    "successful_clients": sum(r["ok"] for r in rows),
                    "completion_ms": stats([r["ms"] for r in rows]),
                    "total_bytes": sum(r["bytes"] for r in rows),
                    "wall_s": round(time.monotonic() - began, 3),
                    "load_generator_cpu_percent": round(
                        (time.process_time() - cpu_start) / (time.monotonic() - began) * 100, 2
                    ),
                    "errors": [
                        {k: r.get(k) for k in ("error", "failed_path", "detail")}
                        for r in rows
                        if not r["ok"]
                    ],
                    "health": health,
                    "scope": "new client downloads, server caches may be warm; no JS execution",
                },
                self.output,
            )

    async def cloud(self, count, wav, rounds):
        with wave.open(str(wav)) as w:
            assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
            pcm = w.readframes(w.getnframes())
        assert len(pcm) <= 16000 * 2 * 15
        pcm += bytes((-len(pcm)) % 1920)
        sockets = []
        rows = []
        monitor_stop = asyncio.Event()
        monitor_task = asyncio.create_task(self.health(monitor_stop))
        try:
            for _ in range(count):
                try:
                    room = await self.claim()
                    ws = await self.socket("voice", room)
                    sockets.append((room, ws))
                except httpx.HTTPStatusError as e:
                    emit(
                        {
                            "phase": "cloud_admission",
                            "requested": count,
                            "admitted": len(sockets),
                            "status": e.response.status_code,
                        },
                        self.output,
                    )
                    break

            async def connect(room, ws):
                began = time.monotonic()
                await ws.send(json.dumps({"type": "connect", "mode": "cloud"}))
                async with asyncio.timeout(40):
                    while True:
                        data = json.loads(await ws.recv())
                        if data.get("type") == "voice_status":
                            state = data.get("state")
                            if state == "ready":
                                return {
                                    "room": room,
                                    "ready": True,
                                    "connect_ms": (time.monotonic() - began) * 1000,
                                }
                            if state in {"error", "awaiting_binding", "busy"}:
                                return {"room": room, "ready": False, "state": state}

            results = await asyncio.gather(
                *(connect(r, w) for r, w in sockets), return_exceptions=True
            )
            rows = [
                r if isinstance(r, dict) else {"ready": False, "error": type(r).__name__}
                for r in results
            ]
            emit(
                {
                    "phase": "cloud_connect",
                    "requested": count,
                    "admitted": len(sockets),
                    "ready": sum(r["ready"] for r in rows),
                    "connections": rows,
                },
                self.output,
            )
            ready = [s for s, r in zip(sockets, rows, strict=True) if r["ready"]]
            for round_number in range(rounds):

                async def turn(room, ws):
                    events = {}
                    audio_frames = 0
                    audio_bytes = 0
                    nonzero = False
                    started = time.monotonic()
                    sent_end = None
                    await ws.send(
                        json.dumps(
                            {
                                "type": "listen_start",
                                "experience": {
                                    "id": str(uuid.uuid4()),
                                    "page": "home",
                                    "traffic": "verification",
                                    "device": "unknown",
                                    "transport": "websocket",
                                    "scene": "unknown",
                                },
                            }
                        )
                    )

                    async def send_audio():
                        nonlocal sent_end
                        t = time.monotonic()
                        for i in range(0, len(pcm), 1920):
                            await ws.send(pcm[i : i + 1920])
                            await asyncio.sleep(
                                max(0, t + (i // 1920 + 1) * 0.06 - time.monotonic())
                            )
                        sent_end = time.monotonic()
                        await ws.send(json.dumps({"type": "listen_stop"}))

                    sender = asyncio.create_task(send_audio())
                    try:
                        async with asyncio.timeout(70):
                            while True:
                                data = json.loads(await ws.recv())
                                kind = data.get("type")
                                now = time.monotonic()
                                if kind == "transcript" and data.get("text"):
                                    key = "stt" if data.get("role") == "user" else "assistant_text"
                                    events.setdefault(key, now)
                                elif kind == "audio":
                                    raw = base64.b64decode(data["pcm"])
                                    audio_frames += 1
                                    audio_bytes += len(raw)
                                    nonzero = nonzero or any(raw)
                                    events.setdefault("first_audio", now)
                                elif kind == "playback_end":
                                    events["reply_end"] = now
                                    if data.get("aborted"):
                                        raise RuntimeError("aborted")
                                    break
                                elif kind == "voice_status" and data.get("state") in {
                                    "error",
                                    "awaiting_binding",
                                }:
                                    raise RuntimeError("voice_error")
                        await sender
                        return {
                            "room": room,
                            "ok": bool(audio_frames and nonzero and "stt" in events),
                            "latency_from_recording_end_ms": {
                                k: round((v - sent_end) * 1000, 2) for k, v in events.items()
                            },
                            "audio_frames": audio_frames,
                            "audio_bytes": audio_bytes,
                            "audio_nonzero": nonzero,
                            "wall_s": round(time.monotonic() - started, 2),
                        }
                    except Exception as e:
                        sender.cancel()
                        await asyncio.gather(sender, return_exceptions=True)
                        return {
                            "room": room,
                            "ok": False,
                            "error": type(e).__name__,
                            "audio_frames": audio_frames,
                            "stt_received": "stt" in events,
                            "wall_s": round(time.monotonic() - started, 2),
                        }

                results = await asyncio.gather(*(turn(r, w) for r, w in ready))
                emit(
                    {
                        "phase": "cloud_turns",
                        "concurrency": len(ready),
                        "round": round_number + 1,
                        "successful": sum(r["ok"] for r in results),
                        "results": results,
                        "input": "disclosed repository synthetic WAV",
                        "output": "real Linx audio received, not speaker playback",
                    },
                    self.output,
                )
                await asyncio.sleep(2)
        finally:
            for _, ws in sockets:
                try:
                    await ws.send(json.dumps({"type": "disconnect"}))
                except Exception:
                    pass
                await ws.close()
            monitor_stop.set()
            emit({"phase": "cloud_health", "requested": count, **await monitor_task}, self.output)


async def main(args):
    args.output.parent.mkdir(parents=True, exist_ok=True)
    p = Probe(args.url, args.output)
    try:
        health = (await p.request("api/health")).json()
        rooms = (await p.request("api/rooms")).json()
        emit(
            {
                "phase": "start",
                "mode": args.mode,
                "release": health.get("release"),
                "rooms_before": rooms,
            },
            args.output,
        )
        if args.mode == "public":
            await p.public(args.counts, args.duration, args.cold)
        else:
            await p.cloud(args.clients, args.wav, args.rounds)
    finally:
        await p.client.aclose()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["public", "cloud"])
    ap.add_argument("--url", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--counts", nargs="+", type=int, default=[10, 50, 100])
    ap.add_argument("--duration", type=int, default=20)
    ap.add_argument("--cold", type=int, default=100)
    ap.add_argument("--clients", type=int, default=2)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument(
        "--wav", type=Path, default=Path("frontend/public/demo-audio/interview-command.wav")
    )
    args = ap.parse_args()
    if (
        not all(1 <= n <= 100 for n in args.counts)
        or not 1 <= args.clients <= 32
        or not 1 <= args.duration <= 120
        or not 0 <= args.cold <= 100
        or not 1 <= args.rounds <= 3
    ):
        ap.error("Bounded probe limits exceeded")
    asyncio.run(main(args))
