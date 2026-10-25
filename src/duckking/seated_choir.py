"""Four seated singers; each real stand gates its authored solo turn."""

import asyncio
import math
import time

from .posture import change_posture, measure_posture, request_posture

SEATED_SECONDS = 40.0
SEATED_SPAWNS = [(-0.05, y) for y in (-0.33, -0.11, 0.11, 0.33)]


def solo_phase(elapsed):
    if elapsed < 4 or elapsed >= 36:
        return "chorus", None
    part = min(3, int((elapsed - 4) // 8))
    beat = elapsed - 4 - part * 8
    return ("rising" if beat < 2 else "solo" if beat < 6 else "sitting"), part


class SeatedChoir:
    def __init__(self, backend):
        self.backend = backend
        self.floor = backend.model.geom("floor").id
        self.table = backend.model.geom("table_top").id
        self.phase = "ready"
        self.error = None
        self.elapsed = 0.0
        self.running = self.music_started = False
        self.solo = None
        self.stood = [None] * 4
        self.returned = [None] * 4
        self.completed_solos = []
        self.max_drift = [0.0] * 4
        self.floor_contacts = [0] * 4
        self.table_contacts = [0] * 4
        self.stable_since = [None] * 4
        self.targets = [None] * 4

    def update(self):
        if not self.running:
            return
        b = self.backend
        for c in b.data.contact:
            for surface, counts in (
                (self.floor, self.floor_contacts),
                (self.table, self.table_contacts),
            ):
                one, two = int(c.geom1), int(c.geom2)
                if surface in (one, two):
                    owner = b.geom_owner[two if one == surface else one]
                    if owner >= 0:
                        counts[owner] += 1
        for i, d in enumerate(b.drivers):
            self.max_drift[i] = max(
                self.max_drift[i], math.dist(b.data.qpos[d.root : d.root + 2], SEATED_SPAWNS[i])
            )

    def stop(self):
        if self.running:
            self.phase = "stopped"
        self.running = False

    def snapshot(self):
        return {
            "phase": self.phase,
            "error": self.error,
            "elapsed": self.elapsed,
            "duration": SEATED_SECONDS,
            "running": self.running,
            "music_started": self.music_started,
            "solo": None if self.solo is None else "abcd"[self.solo],
            "postures": [measure_posture(self.backend, d) for d in self.backend.drivers],
            "standing_confirmations": self.stood.copy(),
            "seated_returns": self.returned.copy(),
            "completed_solos": self.completed_solos.copy(),
            "max_drift_m": self.max_drift.copy(),
            "floor_contacts": self.floor_contacts.copy(),
            "table_contacts": self.table_contacts.copy(),
            "source": "scripted_solos_official_sitstand_real_contacts",
        }

    async def perform(self):
        if self.phase != "ready":
            raise ValueError("请重置轮唱舞台后再开始")
        b = self.backend
        self.running = True
        self.phase = "seating"
        try:
            await change_posture(b, b.drivers, "sit")
            self.music_started = True
            start, sim_start = time.monotonic(), float(b.data.time)
            previous, solo_started = (None, None), None
            while (elapsed := time.monotonic() - start) < SEATED_SECONDS:
                b.ensure_running()
                if elapsed > 2 and b.data.time - sim_start < elapsed * 0.6:
                    ratio = (b.data.time - sim_start) / elapsed
                    raise ValueError(f"坐姿合唱物理推进过慢（{ratio:.2f}×），已停止")
                if max(self.max_drift) > 0.12 or any(self.floor_contacts):
                    raise ValueError("歌手离开安全站位或桌面，合唱已停止")
                self.elapsed = elapsed
                phase, part = solo_phase(elapsed)
                if previous != (phase, part):
                    if previous[0] == "solo":
                        if elapsed - solo_started < 3.5:
                            raise ValueError("独唱时段未完整执行，合唱已停止")
                        self.completed_solos.append("abcd"[previous[1]])
                    if phase == "solo":
                        if self.stood[part] is None:
                            raise ValueError("歌手尚未站稳，独唱没有开始")
                        solo_started = elapsed
                    if phase == "rising" and part and self.returned[part - 1] is None:
                        raise ValueError("上一位歌手尚未坐稳，已停止接唱")
                    if phase == "chorus" and elapsed >= 36 and self.returned[3] is None:
                        raise ValueError("最后一位歌手尚未坐稳，未进入谢幕")
                    previous = phase, part
                self.phase, self.solo = phase, part
                for i, d in enumerate(b.drivers):
                    target = "stand" if i == part and phase in {"rising", "solo"} else "sit"
                    if self.targets[i] != target:
                        self.targets[i], self.stable_since[i] = target, None
                    request_posture(d, target)
                    d.command[4] = (0.12 if phase == "solo" and i == part else 0.06) * math.sin(
                        elapsed * math.tau * 2
                    )
                    d.command[6] = 0.05 * math.sin(elapsed * math.tau)
                    measured = measure_posture(b, d)
                    if measured["observed"] == target:
                        if self.stable_since[i] is None:
                            self.stable_since[i] = float(b.data.time)
                        if b.data.time - self.stable_since[i] >= 0.3:
                            proof = {"at": elapsed, **measured}
                            if i == part and phase == "rising" and self.stood[i] is None:
                                self.stood[i] = proof
                            if i == part and phase == "sitting" and self.returned[i] is None:
                                self.returned[i] = proof
                    else:
                        self.stable_since[i] = None
                        if phase == "solo":
                            raise ValueError("独唱时姿态失稳，音乐和编排已停止")
                await asyncio.sleep(0.02)
            self.elapsed = SEATED_SECONDS
            verified = (
                self.completed_solos == list("abcd")
                and all(self.returned)
                and all(measure_posture(b, d)["observed"] == "sit" for d in b.drivers)
                and not any(self.floor_contacts)
                and all(self.table_contacts)
            )
            self.phase = "completed" if verified else "failed"
            self.running = False
            return {
                **self.snapshot(),
                "verified": verified,
                "message": "四位歌手均已站稳独唱并坐回原位"
                if verified
                else "未完成四鸭坐站轮唱验证",
            }
        except Exception as exc:
            self.phase = "failed"
            self.error = str(exc)
            raise
        finally:
            if self.phase not in {"completed", "failed"}:
                self.phase = "stopped"
            self.running = False
            for d in b.drivers:
                request_posture(d, d.rest_posture)
