"""Four-duck floor show: measured navigation, authored contact reaction and shared beat.

Only reset writes root poses. Motion uses official policy commands; a poke is a
bounded external force, never a visual displacement or a guaranteed fall.
"""

import asyncio
import heapq
import math
import random
import time
import uuid
import xml.etree.ElementTree as ET

import mujoco
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .choreography import sample
from .grasp_model import articulate_mouth
from .idle import yawn_frame
from .posture import change_posture, measure_posture

MEMBERS = "abcd"
SLOTS = [(0.0, y) for y in (-0.69, -0.23, 0.23, 0.69)]
LIMIT = 1.65


class StageSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = Field(pattern="^[abcd]$")
    order: list[str] = Field(default_factory=lambda: list(MEMBERS), min_length=4, max_length=4)
    revision: str
    instance: str

    @model_validator(mode="after")
    def unique_order(self):
        if set(self.order) != set(MEMBERS):
            raise ValueError("屏幕顺序必须恰好包含 A—D")
        return self


def build_stage_model(robot_dir):
    spec = mujoco.MjSpec.from_string(
        '<mujoco><worldbody><geom name="floor" type="plane" size="4 4 .1" '
        'rgba=".83 .87 .78 1" friction="1 .01 .001"/></worldbody></mujoco>'
    )
    for member in MEMBERS:
        root = ET.parse(robot_dir / "robot_allcollisions.xml").getroot()
        root.find("compiler").set("meshdir", str((robot_dir / "assets").resolve()))
        articulate_mouth(root)
        robot = mujoco.MjSpec.from_string(ET.tostring(root, encoding="unicode"))
        spec.attach(robot, prefix=member + "_", frame=spec.worldbody.add_frame())
    model = spec.compile()
    model.opt.timestep = 0.005
    return model


def scatter(seed):
    rng = random.Random(seed)
    positions = []
    for _ in MEMBERS:
        for _attempt in range(1000):
            point = (rng.uniform(-0.95, 0.8), rng.uniform(-1.05, 1.05))
            if all(math.dist(point, p[:2]) > 0.38 for p in positions):
                positions.append((*point, rng.uniform(-math.pi, math.pi)))
                break
        else:
            raise ValueError("无法生成不重叠的初始站位")
    return sorted(positions, key=lambda p: p[1])


def angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def path_to(start, goal, obstacles):
    """Small bounded A* around other actual body positions, in world coordinates."""
    step = 0.10

    def key(p):
        return round(p[0] / step), round(p[1] / step)

    begin, end = key(start), key(goal)
    queue = [(0.0, begin)]
    cost, parents = {begin: 0.0}, {}
    for _ in range(6000):
        if not queue:
            return []
        _, node = heapq.heappop(queue)
        if node == end:
            nodes = [node]
            while node in parents:
                node = parents[node]
                nodes.append(node)
            return [(x * step, y * step) for x, y in reversed(nodes)][1:] + [tuple(goal)]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nxt = node[0] + dx, node[1] + dy
            point = nxt[0] * step, nxt[1] * step
            if max(map(abs, point)) > LIMIT - 0.1:
                continue
            if any(math.dist(point, other) < 0.25 for other in obstacles):
                continue
            value = cost[node] + math.hypot(dx, dy)
            if value >= cost.get(nxt, math.inf):
                continue
            cost[nxt], parents[nxt] = value, node
            heapq.heappush(queue, (value + math.dist(nxt, end), nxt))
    return []


class FloorStage:
    def __init__(self, backend, seed):
        self.b, self.seed = backend, seed
        self.instance = uuid.uuid4().hex
        self.rng = random.Random(seed)
        self.selected = "a"
        self.order = list(MEMBERS)
        self.voice_reference = None
        self.phase = "scattered"
        self.running = False
        self.contacts = set()
        self.reactions = []
        self.arrived = [False] * 4
        self.yawns = [0] * 4
        self.mouths = [backend.model.actuator(c + "_mouth").id for c in MEMBERS]
        self.last_roll = None
        self.last_dance = None
        self.pokes = 0

    def select(self, selection):
        if selection.revision != self.b.revision or selection.instance != self.instance:
            raise ValueError("舞台已重置，请重新点选")
        self.selected, self.order = selection.target, selection.order
        return self.snapshot()

    def capture_reference(self):
        self.voice_reference = (self.selected, self.order[0])

    def member(self, target):
        return (
            self.selected
            if target == "selected"
            else self.order[0]
            if target == "leftmost"
            else target
        )

    def positions(self):
        return [d.pose(self.b.data)[0][:2] for d in self.b.drivers]

    def update_contacts(self):
        pairs = set()
        for c in self.b.data.contact:
            a, b = self.b.geom_owner[c.geom1], self.b.geom_owner[c.geom2]
            if a >= 0 and b >= 0 and a != b:
                pairs.add(tuple(sorted((a, b))))
        self.contacts |= pairs

    def stop(self):
        self.running = False
        self.b.data.xfrc_applied[:] = 0
        self.b.data.ctrl[self.mouths] = 0
        if self.phase not in {"scattered", "lined_up", "completed", "failed"}:
            self.phase = "stopped"

    def guard(self):
        self.b.ensure_running()
        for d, p in zip(self.b.drivers, self.positions(), strict=True):
            if max(map(abs, p)) > LIMIT or self.b.data.xmat[d.body, 8] < 0.75:
                raise ValueError("小鸭越界或失稳，群体任务已停止，请重新散落后重试")

    async def delay(self, duration):
        start, deadline = float(self.b.data.time), time.monotonic() + duration * 4 + 3
        while self.b.data.time - start < duration:
            self.guard()
            if time.monotonic() > deadline:
                raise ValueError("四鸭仿真推进超时")
            await asyncio.sleep(0.02)

    def clear_commands(self):
        for d in self.b.drivers:
            d.command[:] = 0
        self.b.data.ctrl[self.mouths] = 0

    def steer(self, index, point, *, final=False, yaw=0.0):
        d = self.b.drivers[index]
        pos, heading = d.pose(self.b.data)
        dx, dy = point[0] - pos[0], point[1] - pos[1]
        distance = math.hypot(dx, dy)
        d.command[:] = 0
        if distance < 0.10:
            error = angle(yaw - heading)
            if final and abs(error) > 0.25:
                d.command[2] = math.copysign(max(0.5, min(0.8, abs(error) * 2.5)), error)
                return False
            return True
        error = angle(math.atan2(dy, dx) - heading)
        d.command[2] = max(-1.0, min(1.0, error * 2.5))
        if abs(error) < 0.50:
            d.command[0] = min(0.34, max(0.15, distance * 1.5)) * max(0.35, math.cos(error))
        return False

    async def navigate(self, indices, goals, max_seconds=38, expressive=False):
        paths = {i: [] for i in indices}
        replanned = -math.inf
        stable = None
        start, wall = float(self.b.data.time), time.monotonic()
        reaction_done = False
        holding = set()
        aligning = set()
        while True:
            self.guard()
            elapsed = float(self.b.data.time) - start
            if elapsed > max_seconds or time.monotonic() - wall > max_seconds * 2 + 5:
                raise ValueError("集结未在时限内完成，请重新散落后重试")
            if expressive and self.contacts and not reaction_done:
                pair = sorted(self.contacts)[0]
                chosen = self.rng.choice(pair)
                self.clear_commands()
                self.phase = "contact_sit"
                seated = await change_posture(self.b, [self.b.drivers[chosen]], "sit")
                self.reactions.append(
                    {"pair": [MEMBERS[i] for i in pair], "member": MEMBERS[chosen], "sit": seated}
                )
                await self.delay(0.45)
                standing = await change_posture(self.b, [self.b.drivers[chosen]], "stand")
                self.reactions[-1]["stand"] = standing
                self.b.drivers[chosen].policy = "walk"
                holding.discard(chosen)
                aligning.discard(chosen)
                reaction_done = True
                self.phase = "gathering"
                replanned = -math.inf
            positions = self.positions()
            if elapsed - replanned > 0.65:
                for i in indices:
                    paths[i] = path_to(
                        positions[i], goals[i], [p for j, p in enumerate(positions) if j != i]
                    )
                replanned = elapsed
            done = []
            for i in indices:
                d = self.b.drivers[i]
                d.policy = "walk"
                if i in holding and math.dist(positions[i], goals[i]) > 0.18:
                    holding.remove(i)
                if i in holding:
                    d.command[:] = 0
                    d.policy = "sitstand"
                    d.posture_target = d.rest_posture = "stand"
                    done.append(True)
                    continue
                distance = math.dist(positions[i], goals[i])
                if distance < 0.09:
                    aligning.add(i)
                if i in aligning:
                    d.command[:] = 0
                    error = angle(-d.pose(self.b.data)[1])
                    if distance > 0.18:
                        aligning.remove(i)
                    elif abs(error) > 0.14:
                        d.command[2] = math.copysign(0.75, error)
                        done.append(False)
                        continue
                    else:
                        holding.add(i)
                        d.policy = "sitstand"
                        d.posture_target = d.rest_posture = "stand"
                        done.append(True)
                        continue
                near = math.dist(positions[i], goals[i]) < 0.13
                route = paths[i]
                while len(route) > 1 and math.dist(positions[i], route[0]) < 0.12:
                    route.pop(0)
                if near or route:
                    arrived = self.steer(i, goals[i] if near else route[0], final=near)
                    arrived = arrived and near
                else:
                    d.command[:] = 0
                    arrived = False
                if arrived and distance < 0.13:
                    holding.add(i)
                    d.command[:] = 0
                    d.policy = "sitstand"
                    d.posture_target = d.rest_posture = "stand"
                done.append(arrived)
            if expressive:
                for i, d in enumerate(self.b.drivers):
                    opening = elapsed - i * 0.7 - 1
                    if 0 < opening < 4:
                        pitch, mouth = yawn_frame(opening)
                        d.command[4] = pitch * 0.45
                        self.b.data.ctrl[self.mouths[i]] = mouth
                        self.yawns[i] = 1
                    else:
                        self.b.data.ctrl[self.mouths[i]] = 0
            supported = all(
                measure_posture(self.b, self.b.drivers[i])["observed"] == "stand" for i in indices
            )
            if all(done) and supported and (not expressive or elapsed >= 7.2):
                stable = float(self.b.data.time) if stable is None else stable
                if self.b.data.time - stable > 0.35:
                    break
            else:
                stable = None
            await asyncio.sleep(0.02)
        self.clear_commands()

    async def gather(self):
        self.phase = "gathering"
        self.arrived = [False] * 4
        self.contacts.clear()
        await self.navigate(list(range(4)), dict(enumerate(SLOTS)), expressive=True)
        self.arrived = [True] * 4
        self.phase = "lined_up"
        return {"verified": True, **self.snapshot(), "running": False}

    def require_line(self):
        if not all(self.arrived) or any(
            math.dist(p, slot) > 0.18 for p, slot in zip(self.positions(), SLOTS, strict=True)
        ):
            raise ValueError("请先让四鸭集结排队，当前未确认全部归位")
        self.guard()

    async def roll(self, member):
        self.require_line()
        index = MEMBERS.index(member)
        self.selected = member
        d = self.b.drivers[index]
        anchors = self.positions()
        self.phase = "rolling"
        # Same official one-shot, now measured for the selected prefixed robot.
        d.command[:] = 0
        d.policy = "roulade"
        d.phase_started = float(self.b.data.time)
        d.until = d.phase_started + 2
        last, rotation, low = 0.0, 0.0, 1.0
        min_rotation = max_rotation = 0.0
        start = float(self.b.data.time)
        deadline = time.monotonic() + 15
        while self.b.data.time - start < 6:
            self.b.ensure_running()
            if time.monotonic() > deadline:
                raise ValueError("前滚翻推进超时")
            rot = self.b.data.xmat[d.body].reshape(3, 3)
            current = math.atan2(-rot[2, 0], rot[2, 2])
            rotation += angle(current - last)
            last = current
            min_rotation, max_rotation = min(min_rotation, rotation), max(max_rotation, rotation)
            low = min(low, float(rot[2, 2]))
            if any(
                math.dist(p, anchors[j]) > 0.12
                for j, p in enumerate(self.positions())
                if j != index
            ):
                raise ValueError("候场鸭偏离原位，前滚翻已停止")
            await asyncio.sleep(0.02)
        pose = measure_posture(self.b, d)
        if low >= -0.5 or max_rotation - min_rotation < 5 or pose["observed"] != "stand":
            raise ValueError("未确认完整前滚翻和恢复站稳")
        self.phase = "returning"
        await self.navigate([index], {index: SLOTS[index]}, max_seconds=18)
        self.last_roll = {
            "member": member,
            "rotation_rad": max_rotation - min_rotation,
            "min_upright": low,
            "standing": pose,
            "returned": True,
        }
        self.phase = "lined_up"
        return {"verified": True, **self.last_roll}

    async def dance(self):
        self.require_line()
        self.phase = "dancing"
        start = float(self.b.data.time)
        deadline = time.monotonic() + 25
        phases = []
        while (elapsed := float(self.b.data.time) - start) < 7:
            self.guard()
            if time.monotonic() > deadline:
                raise ValueError("齐舞推进超时")
            if elapsed < 3:
                name, t = "flash_step", elapsed
            elif elapsed < 4:
                name, t = "flash_step", 3
            else:
                name, t = "bear_shake", elapsed - 4
            frame = sample(name, t)
            phase = name + ":" + frame.phase
            if not phases or phases[-1] != phase:
                phases.append(phase)
            for d in self.b.drivers:
                d.policy = "walk"
                d.command[:] = 0
                d.command[:3] = [frame.forward, frame.lateral, frame.turn]
                d.command[4:7] = [frame.head_pitch, frame.head_yaw, frame.head_roll]
                if frame.body_active:
                    d.command[9:12] = [frame.body_z, frame.body_roll, frame.body_pitch]
            await asyncio.sleep(0.02)
        self.clear_commands()
        await self.delay(0.5)
        postures = [measure_posture(self.b, d) for d in self.b.drivers]
        if any(p["observed"] != "stand" for p in postures):
            raise ValueError("齐舞后未确认四鸭全部站稳")
        self.last_dance = {
            "members": list(MEMBERS),
            "phases": phases,
            "clock": "shared_mujoco_sim_time",
            "stable": True,
            "postures": postures,
        }
        self.phase = "completed"
        self.arrived = [False] * 4
        return {"verified": True, **self.last_dance}

    async def poke(self, member):
        self.selected = member
        d = self.b.drivers[MEMBERS.index(member)]
        self.phase = "poking"
        try:
            self.b.data.xfrc_applied[d.body, :3] = [1.0, 0, 0]
            await self.delay(0.08)
        finally:
            self.b.data.xfrc_applied[:] = 0
        self.pokes += 1
        self.arrived = [False] * 4
        self.phase = "scattered"
        return {
            "verified": True,
            "member": member,
            "force_n": 1.0,
            "duration_sim_s": 0.08,
            "message": "已施加短促物理推力，不保证跌倒",
        }

    async def perform(self, operation, member="a"):
        self.running = True
        try:
            result = (
                await getattr(self, operation)(member)
                if operation in {"roll", "poke"}
                else await getattr(self, operation)()
            )
            return result
        except asyncio.CancelledError:
            self.phase = "stopped"
            raise
        except Exception:
            self.phase = "failed"
            raise
        finally:
            self.running = False
            self.clear_commands()
            self.b.data.xfrc_applied[:] = 0

    def snapshot(self):
        return {
            "phase": self.phase,
            "running": self.running,
            "seed": self.seed,
            "instance": self.instance,
            "selected": self.selected,
            "screen_order": self.order,
            "slots": SLOTS,
            "arrived": self.arrived.copy(),
            "yawns": self.yawns.copy(),
            "contact_pairs": [[MEMBERS[i] for i in pair] for pair in sorted(self.contacts)],
            "reactions": self.reactions.copy(),
            "roll": self.last_roll,
            "dance": self.last_dance,
            "pokes": self.pokes,
            "source": "local_group_orchestration_official_onnx_real_contacts",
        }
