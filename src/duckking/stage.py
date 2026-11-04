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
from typing import Literal

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
    target: Literal["a", "b", "c", "d"] | None = None
    targets: list[Literal["a", "b", "c", "d"]] | None = Field(default=None, max_length=4)
    operation: Literal["set", "toggle", "order"] = "set"
    order: list[str] = Field(default_factory=lambda: list(MEMBERS), min_length=4, max_length=4)
    revision: str
    instance: str

    @model_validator(mode="after")
    def unique_order(self):
        if set(self.order) != set(MEMBERS):
            raise ValueError("屏幕顺序必须恰好包含 A—D")
        if self.operation == "toggle":
            if self.target is None or self.targets is not None:
                raise ValueError("切换选择需要一个目标")
        elif self.operation == "order":
            if self.target is not None or self.targets is not None:
                raise ValueError("更新屏幕顺序不能改变选择")
        elif (self.target is None) == (self.targets is None):
            raise ValueError("请提供单个目标或完整选择集合")
        if self.targets is not None and len(set(self.targets)) != len(self.targets):
            raise ValueError("选择集合不能重复")
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
        self.selected = []
        self.selection_version = 0
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
        self.roll_runs = None
        self.last_dance = None
        self.pokes = 0

    def select(self, selection):
        if selection.revision != self.b.revision or selection.instance != self.instance:
            raise ValueError("舞台已重置，请重新点选")
        if selection.operation == "toggle":
            if selection.target in self.selected:
                self.selected.remove(selection.target)
            else:
                self.selected.append(selection.target)
        elif selection.operation == "set":
            self.selected = (
                list(selection.targets) if selection.targets is not None else [selection.target]
            )
        self.selected = [c for c in MEMBERS if c in self.selected]
        self.order = selection.order.copy()
        self.selection_version += 1
        return self.snapshot()

    def capture_reference(self):
        self.voice_reference = (tuple(self.selected), self.order[0])

    def members(self, target):
        chosen = (
            self.selected.copy()
            if target == "selected"
            else [self.order[0] if target == "leftmost" else target]
        )
        if not chosen:
            raise ValueError("请先用指挥棒或勾选框选中要表演的鸭子")
        return chosen

    def member(self, target):
        chosen = self.members(target)
        if len(chosen) != 1:
            raise ValueError("轻戳一次只能指定一只鸭子")
        return chosen[0]

    def positions(self):
        return [d.pose(self.b.data)[0][:2] for d in self.b.drivers]

    def update_contacts(self):
        # Measure rotations on every physics step; async/network scheduling must
        # not skip the inversion or unwrap a whole somersault as a short turn.
        if self.roll_runs is not None:
            for i, run in self.roll_runs.items():
                rot = self.b.data.xmat[self.b.drivers[i].body].reshape(3, 3)
                current = math.atan2(-rot[2, 0], rot[2, 2])
                run["rotation"] += angle(current - run["last"])
                run["last"] = current
                run["minimum"] = min(run["minimum"], run["rotation"])
                run["maximum"] = max(run["maximum"], run["rotation"])
                run["low"] = min(run["low"], float(rot[2, 2]))
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
                involved = [i for i in pair if i in indices]
                chosen = self.rng.choice(involved) if involved else None
                if chosen is None:
                    self.contacts.discard(pair)
                    continue
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
                for i in indices:
                    d = self.b.drivers[i]
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

    async def posture(self, indices, target):
        drivers = [self.b.drivers[i] for i in indices]
        changing = [d for d in drivers if measure_posture(self.b, d)["observed"] != target]
        if changing:
            result = await change_posture(self.b, changing, target)
        else:
            result = {"verified": True, "posture": target}
        # Keep supported sitting/standing robots on the posture policy while idle.
        for d in drivers:
            d.command[:] = 0
            d.policy = "sitstand"
            d.posture_target = d.rest_posture = target
        return {
            **result,
            "members": [MEMBERS[i] for i in indices],
            "ducks": [measure_posture(self.b, d) for d in drivers],
        }

    async def gather(self, members):
        indices = [MEMBERS.index(member) for member in members]
        self.contacts.clear()
        self.phase = "gather_rising"
        standing = await self.posture(indices, "stand")
        for i in indices:
            self.arrived[i] = False
        self.phase = "gathering"
        await self.navigate(indices, {i: SLOTS[i] for i in indices}, expressive=True)
        self.phase = "gather_sitting"
        seated = await self.posture(indices, "sit")
        for i in indices:
            self.arrived[i] = True
        self.phase = "lined_up"
        return {
            "verified": True,
            **self.snapshot(),
            "running": False,
            "members": members.copy(),
            "standing": standing,
            "seated": seated,
        }

    def require_ready(self):
        self.guard()
        if any(
            measure_posture(self.b, d)["observed"] not in {"sit", "stand"} for d in self.b.drivers
        ):
            raise ValueError("请等待四鸭坐稳或站稳后再表演")

    async def roll(self, members):
        self.require_ready()
        self.phase = "roll_rising"
        standing = await self.posture(list(range(4)), "stand")
        indices = [MEMBERS.index(member) for member in members]
        # Sitstand ends with straight knees; settle the selected robots on
        # velstand before entering the rolling policy, as for the kick handoff.
        for i in indices:
            self.b.drivers[i].policy = "walk"
        await self.delay(0.5)
        # A policy handoff must use a settled trained stance, not the first
        # upright instant after a sitstand transition or a moving gait phase.
        stable_since = None
        stable_deadline = time.monotonic() + 4
        while True:
            self.guard()
            settled = all(
                measure_posture(self.b, self.b.drivers[i])["observed"] == "stand"
                and math.hypot(
                    *self.b.data.qvel[
                        self.b.model.jnt_dofadr[
                            self.b.model.joint(MEMBERS[i] + "_trunk_base_freejoint").id
                        ] : self.b.model.jnt_dofadr[
                            self.b.model.joint(MEMBERS[i] + "_trunk_base_freejoint").id
                        ]
                        + 2
                    ]
                )
                < 0.08
                for i in indices
            )
            if settled:
                stable_since = self.b.data.time if stable_since is None else stable_since
                if self.b.data.time - stable_since >= 0.3:
                    break
            else:
                stable_since = None
            if time.monotonic() > stable_deadline:
                raise ValueError("翻滚前尚未稳定到策略站姿")
            await asyncio.sleep(0.02)
        anchors = self.positions()
        self.phase = "rolling"
        runs = {}
        start = float(self.b.data.time)
        for i in indices:
            d = self.b.drivers[i]
            d.command[:] = 0
            d.policy = "roulade"
            d.phase_started, d.until = start, start + 2
            runs[i] = {"last": 0.0, "rotation": 0.0, "minimum": 0.0, "maximum": 0.0, "low": 1.0}
        self.roll_runs = runs
        deadline = time.monotonic() + 15
        while self.b.data.time - start < 6:
            self.b.ensure_running()
            if time.monotonic() > deadline:
                raise ValueError("前滚翻推进超时")
            if any(
                math.dist(p, anchors[j]) > 0.12
                for j, p in enumerate(self.positions())
                if j not in runs
            ):
                raise ValueError("候场鸭偏离原位，前滚翻已停止")
            await asyncio.sleep(0.02)
        for i, run in runs.items():
            rotation = run["maximum"] - run["minimum"]
            if run["low"] >= -0.5 or rotation < 5:
                raise ValueError(
                    f"未确认鸭 {MEMBERS[i].upper()} 完整前滚翻"
                    f"（旋转 {rotation:.2f} rad，倒置 {run['low']:.2f}）"
                )
        self.phase = "roll_recovering"
        recovered = await self.posture(indices, "stand")
        results = [
            {
                "member": MEMBERS[i],
                "rotation_rad": run["maximum"] - run["minimum"],
                "min_upright": run["low"],
                "standing": recovered["ducks"][j],
                "returned": False,
            }
            for j, (i, run) in enumerate(runs.items())
        ]
        self.phase = "roll_sitting"
        seated = await self.posture(indices, "sit")
        for i in indices:
            self.arrived[i] = False
        self.last_roll = {
            "members": members.copy(),
            "results": results,
            "standing": standing,
            "seated": seated,
            "returned": False,
            "rotation_rad": min(r["rotation_rad"] for r in results),
        }
        if len(results) == 1:
            self.last_roll.update(results[0])
        self.phase = "completed"
        return {"verified": True, **self.last_roll}

    async def dance(self, members):
        self.require_ready()
        indices = [MEMBERS.index(member) for member in members]
        self.phase = "dance_rising"
        standing = await self.posture(indices, "stand")
        anchors = self.positions()
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
            if any(
                math.dist(p, anchors[j]) > 0.12
                for j, p in enumerate(self.positions())
                if j not in indices
            ):
                raise ValueError("候场鸭偏离原位，齐舞已停止")
            for i in indices:
                d = self.b.drivers[i]
                d.policy = "walk"
                d.command[:] = 0
                d.command[:3] = [frame.forward, frame.lateral, frame.turn]
                d.command[4:7] = [frame.head_pitch, frame.head_yaw, frame.head_roll]
                if frame.body_active:
                    d.command[9:12] = [frame.body_z, frame.body_roll, frame.body_pitch]
            await asyncio.sleep(0.02)
        self.clear_commands()
        await self.delay(0.5)
        postures = [measure_posture(self.b, self.b.drivers[i]) for i in indices]
        if any(p["observed"] != "stand" for p in postures):
            raise ValueError("齐舞后未确认选中鸭全部站稳")
        self.last_dance = {
            "members": members.copy(),
            "standing": standing,
            "phases": phases,
            "clock": "shared_mujoco_sim_time",
            "stable": True,
            "postures": postures,
        }
        self.phase = "completed"
        for i in indices:
            self.arrived[i] = False
        return {"verified": True, **self.last_dance}

    async def poke(self, member):
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
                if operation in {"gather", "roll", "dance", "poke"}
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
            self.roll_runs = None
            self.running = False
            self.clear_commands()
            self.b.data.xfrc_applied[:] = 0

    def snapshot(self):
        return {
            "phase": self.phase,
            "running": self.running,
            "seed": self.seed,
            "instance": self.instance,
            "selected": self.selected.copy(),
            "selection_version": self.selection_version,
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
