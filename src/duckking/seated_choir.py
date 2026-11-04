"""Four seated singers; each real stand gates its authored solo turn."""

import asyncio
import math
import time

from .posture import change_posture, measure_posture, request_posture

SEATED_SECONDS = 40.0
LIVE_SOLO_SECONDS = 8.0
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
        self.live = False
        self.performance_id = 0
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
            "live": self.live,
            "performance_id": self.performance_id,
            "error": self.error,
            "elapsed": self.elapsed,
            "duration": LIVE_SOLO_SECONDS if self.live else SEATED_SECONDS,
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

    async def single(self, member):
        """A named live solo, never a timer masquerading as a confirmed stand."""
        b = self.backend
        index = "abcd".index(member)
        if any(measure_posture(b, d)["observed"] != "sit" for d in b.drivers):
            raise ValueError("请先让四位歌手坐稳，再开始独唱")
        self.live = self.running = True
        self.music_started = False
        self.error = None
        self.performance_id += 1
        self.solo = index
        self.elapsed = 0
        self.phase = "rising"
        try:
            standing = await change_posture(b, [b.drivers[index]], "stand")
            if not standing["verified"]:
                raise ValueError("独唱者未站稳")
            self.stood[index] = standing
            self.phase = "solo"
            self.music_started = True
            start = time.monotonic()
            while time.monotonic() - start < LIVE_SOLO_SECONDS:
                b.ensure_running()
                self.elapsed = time.monotonic() - start
                if any(self.floor_contacts) or max(self.max_drift) > .12:
                    raise ValueError("歌手离开安全站位，独唱停止")
                for i, driver in enumerate(b.drivers):
                    expected = "stand" if i == index else "sit"
                    if measure_posture(b, driver)["observed"] != expected:
                        raise ValueError("歌手姿态未保持，独唱停止")
                    driver.command[4] = .08 * math.sin(self.elapsed * math.tau * 2)
                await asyncio.sleep(.02)
            self.music_started = False
            self.phase = "sitting"
            seated = await change_posture(b, [b.drivers[index]], "sit")
            if not seated["verified"]:
                raise ValueError("独唱结束，但歌手尚未坐稳")
            self.returned[index] = seated
            self.completed_solos.append(member)
            self.completed_solos = self.completed_solos[-16:]
            self.phase = "completed"
            return {"verified": True, "member": member, "standing": standing,
                    "seated": seated, "message": "已站稳独唱并坐回"}
        except Exception as exc:
            self.phase, self.error = "failed", str(exc)
            raise
        finally:
            self.running = self.music_started = False
            if self.phase not in {"completed", "failed"}:
                self.phase = "stopped"
            for driver in b.drivers:
                request_posture(driver, driver.rest_posture)

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
