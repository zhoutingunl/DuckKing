"""Four official robots on a finite table; the fall is contact + gravity.

The departure toward the edge is authored choreography, not autonomous error
discovery. Root positions are set only by the explicit scene reset.
"""

import asyncio
import math
import time

import mujoco

TABLE_HEIGHT = 0.40
SHOW_DURATION = 36.0
TEMPO = 72
SPAWNS = [(-0.05, -0.33), (-0.05, -0.11), (-0.05, 0.11), (0.30, 0.33)]


def dance_command(driver, data, index, elapsed, *, anchor=None, heading=0.0):
    """Alternate four beats of real stepping with four beats of standing sway.

    Feedback is a bounded velocity request to the official policy, never a
    correction to qpos. Standing body poses must be zero during walking.
    """
    position, yaw = driver.pose(data)
    x, y = SPAWNS[index] if anchor is None else anchor
    if math.hypot(position[0] - x, position[1] - y) > 0.14:
        raise ValueError("踏步偏离站位过远，表演已停止，请重置场景")
    beat = elapsed * TEMPO / 60 * math.tau
    if int(elapsed * TEMPO / 60 / 4) % 2:
        driver.command[4] = 0.10 * math.sin(beat)
        driver.command[6] = 0.09 * math.sin(beat / 2)
        driver.command[10] = 0.17 * math.sin(beat / 2)
        driver.command[11] = 0.10 * math.cos(beat / 2)
        return
    dx, dy = position[0] - x, position[1] - y
    forward = math.cos(heading) * dx + math.sin(heading) * dy
    sideways = -math.sin(heading) * dx + math.cos(heading) * dy
    vx = max(-0.4, min(0.4, (0.04 * math.sin(beat / 2) - forward) * 8))
    if abs(vx) >= 0.05:
        vx = math.copysign(max(0.26, abs(vx)), vx)
    vy = max(-0.22, min(0.22, -sideways * 4))
    yaw = math.atan2(math.sin(yaw - heading), math.cos(yaw - heading))
    driver.command[:3] = (
        math.cos(yaw) * vx + math.sin(yaw) * vy,
        -math.sin(yaw) * vx + math.cos(yaw) * vy,
        max(-0.5, min(0.5, -yaw * 3)),
    )


def build_table_model(robot_dir):
    spec = mujoco.MjSpec.from_string(
        '<mujoco><worldbody><geom name="floor" type="plane" size="4 4 .1" '
        'rgba=".83 .87 .78 1"/><geom name="table_top" type="box" '
        'pos="0 0 .38" size=".45 .52 .02" group="2" '
        'rgba=".55 .36 .18 1" friction="1 .01 .001"/></worldbody></mujoco>'
    )
    for x in (-0.37, 0.37):
        for y in (-0.44, 0.44):
            spec.worldbody.add_geom(
                name=f"table_leg_{x}_{y}",
                type=mujoco.mjtGeom.mjGEOM_BOX,
                pos=[x, y, 0.18],
                size=[0.025, 0.025, 0.18],
                group=2,
                rgba=[0.30, 0.23, 0.15, 1],
            )
    for name in "abcd":
        robot = mujoco.MjSpec.from_file(str(robot_dir / "robot_allcollisions.xml"))
        spec.attach(robot, prefix=name + "_", frame=spec.worldbody.add_frame())
    model = spec.compile()
    model.opt.timestep = 0.005
    return model


class TableChoir:
    def __init__(self, backend):
        self.backend = backend
        self.table = backend.model.geom("table_top").id
        self.floor = backend.model.geom("floor").id
        self.phase = "ready"
        self.elapsed = 0.0
        self.running = False
        self.table_samples = [0] * 4
        self.ground_samples = [0] * 4
        self.supported = [False] * 4
        self.dropped_at = None
        self.landed_at = None
        self.min_z = [float("inf")] * 4
        self.feet = [
            [backend.model.body(c + "_ankle_" + s).id for s in ("left", "right")] for c in "abcd"
        ]
        self.motion_min = [[float("inf")] * 4 for _ in range(4)]
        self.motion_max = [[float("-inf")] * 4 for _ in range(4)]
        self.max_drift = [0.0] * 4
        self.floor_anchor = None
        self.floor_heading = 0.0
        self.floor_dance_at = None
        self.floor_stable_since = None
        self.floor_min = [float("inf")] * 4
        self.floor_max = [float("-inf")] * 4
        self.floor_drift = 0.0
        self.sim_start = None

    def update(self):
        b = self.backend
        self.supported = [False] * 4
        for contact in b.data.contact:
            one, two = int(contact.geom1), int(contact.geom2)
            for surface, samples in (
                (self.table, self.table_samples),
                (self.floor, self.ground_samples),
            ):
                if surface not in (one, two):
                    continue
                owner = b.geom_owner[two if one == surface else one]
                if owner >= 0:
                    samples[owner] += 1
                    if surface == self.table:
                        self.supported[owner] = True
        for i, driver in enumerate(b.drivers):
            z = float(b.data.qpos[driver.root + 2])
            self.min_z[i] = min(self.min_z[i], z)
            # Exclude the authored departure and fall from dance measurements.
            if self.running and (i < 3 or self.elapsed < 16):
                values = [float(b.data.qpos[driver.q[j]]) for j in (3, 12)] + [
                    float(b.data.xpos[j, 2]) for j in self.feet[i]
                ]
                for j, value in enumerate(values):
                    self.motion_min[i][j] = min(self.motion_min[i][j], value)
                    self.motion_max[i][j] = max(self.motion_max[i][j], value)
                pos, _ = driver.pose(b.data)
                self.max_drift[i] = max(
                    self.max_drift[i], math.hypot(pos[0] - SPAWNS[i][0], pos[1] - SPAWNS[i][1])
                )
            if self.running and i == 3:
                if self.floor_dance_at is not None:
                    values = [float(b.data.qpos[driver.q[j]]) for j in (3, 12)] + [
                        float(b.data.xpos[j, 2]) for j in self.feet[i]
                    ]
                    for j, value in enumerate(values):
                        self.floor_min[j] = min(self.floor_min[j], value)
                        self.floor_max[j] = max(self.floor_max[j], value)
                    pos, _ = driver.pose(b.data)
                    self.floor_drift = max(self.floor_drift, math.dist(pos[:2], self.floor_anchor))
                if self.dropped_at is None and z < TABLE_HEIGHT - 0.06 and not self.supported[i]:
                    self.dropped_at = self.elapsed
                if (
                    self.dropped_at is not None
                    and self.landed_at is None
                    and self.ground_samples[i]
                ):
                    self.landed_at = self.elapsed

    def stop(self):
        if self.running:
            self.phase = "stopped"
        self.running = False

    def snapshot(self):
        return {
            "phase": self.phase,
            "elapsed": self.elapsed,
            "duration": SHOW_DURATION,
            "tempo": TEMPO,
            "running": self.running,
            "table_height_m": TABLE_HEIGHT,
            "falling_duck": "d",
            "dropped_at": self.dropped_at,
            "landed_at": self.landed_at,
            "table_contacts": self.table_samples.copy(),
            "ground_contacts": self.ground_samples.copy(),
            "supported": self.supported.copy(),
            "min_root_height_m": self.min_z.copy(),
            "knee_excursion_deg": [
                [math.degrees(max(0, hi - lo)) for lo, hi in zip(low[:2], high[:2], strict=True)]
                for low, high in zip(self.motion_min, self.motion_max, strict=True)
            ],
            "ankle_vertical_excursion_m": [
                [max(0, hi - lo) for lo, hi in zip(low[2:], high[2:], strict=True)]
                for low, high in zip(self.motion_min, self.motion_max, strict=True)
            ],
            "dance_max_drift_m": self.max_drift.copy(),
            "floor_dance": {
                "started_at": self.floor_dance_at,
                "knee_excursion_deg": [
                    math.degrees(max(0, self.floor_max[j] - self.floor_min[j])) for j in (0, 1)
                ],
                "ankle_vertical_excursion_m": [
                    max(0, self.floor_max[j] - self.floor_min[j]) for j in (2, 3)
                ],
                "max_drift_m": self.floor_drift,
            },
            "source": "scripted_gait_real_contacts_gravity",
        }

    def step(self):
        """One policy command per 20 ms physics tick, independent of UI pacing."""
        if not self.running or self.sim_start is None:
            return
        b = self.backend
        elapsed = float(b.data.time) - self.sim_start
        self.elapsed = elapsed
        reaction = self.dropped_at is not None and elapsed - self.dropped_at < 1.2
        self.phase = (
            "surprised"
            if reaction
            else "rejoin"
            if self.landed_at is not None
            else "edge"
            if elapsed >= 16
            else "singing"
        )
        for i, driver in enumerate(b.drivers):
            driver.command[:] = 0
            if i == 3 and self.dropped_at is not None:
                if self.landed_at is not None and elapsed - self.landed_at > 1.2:
                    position, yaw = driver.pose(b.data)
                    upright = position[2] > 0.10 and b.data.xmat[driver.body, 8] > 0.85
                    if self.floor_dance_at is None:
                        if not upright:
                            self.floor_stable_since = None
                        elif self.floor_stable_since is None:
                            self.floor_stable_since = elapsed
                        elif elapsed - self.floor_stable_since >= 0.4:
                            self.floor_anchor = tuple(position[:2])
                            self.floor_heading = yaw
                            self.floor_dance_at = elapsed
                    if self.floor_dance_at is not None:
                        dance_command(
                            driver,
                            b.data,
                            i,
                            elapsed,
                            anchor=self.floor_anchor,
                            heading=self.floor_heading,
                        )
                continue
            if not reaction:
                if i < 3 or elapsed < 16:
                    dance_command(driver, b.data, i, elapsed)
            else:
                driver.command[5] = 0.30
            # A bounded forward gait crosses the real table edge. No
            # force impulse, root teleport, or moving floor is applied.
            if i == 3 and 16 <= elapsed < 19:
                driver.command[:] = 0
                driver.command[0] = 0.35

    async def perform(self):
        b = self.backend
        if self.phase != "ready" or not all(self.supported):
            raise ValueError("请重置桌上合唱场景，确认四只鸭都站在桌面上")
        self.running = True
        self.phase = "singing"
        start = time.monotonic()
        self.sim_start = float(b.data.time)
        try:
            self.step()
            while b.data.time - self.sim_start < SHOW_DURATION:
                b.ensure_running()
                wall_elapsed = time.monotonic() - start
                if wall_elapsed > 2 and b.data.time - self.sim_start < wall_elapsed * 0.5:
                    raise ValueError("桌上表演物理推进过慢，已停止，请重演")
                await asyncio.sleep(0.02)
            self.elapsed = SHOW_DURATION
            verified = bool(
                self.dropped_at is not None
                and self.landed_at is not None
                and all(self.supported[:3])
                and self.ground_samples[3] > 0
                and not any(self.ground_samples[:3])
                and self.floor_dance_at is not None
                and min(self.floor_max[j] - self.floor_min[j] for j in (0, 1)) > math.radians(25)
            )
            self.phase = "completed" if verified else "failed"
            self.running = False
            return {
                **self.snapshot(),
                "verified": verified,
                "message": "鸭 D 已真实落地并恢复踏步，其余三只留在桌上"
                if verified
                else "未确认单鸭离桌落地或其余成员留在桌上，请重演",
            }
        finally:
            if self.phase not in {"completed", "failed"}:
                self.phase = "stopped"
            self.running = False
            for driver in b.drivers:
                driver.command[:] = 0
