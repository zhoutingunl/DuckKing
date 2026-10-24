"""CPU MuJoCo scenes using Pollen's MJCF and ONNX policies, independently of robotd.

Observation layout, home pose and 50 Hz inference follow microduck_rl/infer_policy.py
(Apache-2.0, Pollen Robotics). Assets remain external; see THIRD_PARTY.md.
"""

import asyncio
import math
import time
import uuid
from contextlib import suppress
from pathlib import Path

import mujoco
import numpy as np
import onnxruntime as ort

from .grasp import BeakGrasp
from .grasp_model import build_grasp_model
from .model_assets import geometry

POLICY_JOINTS = (
    "left_hip_yaw",
    "left_hip_roll",
    "left_hip_pitch",
    "left_knee",
    "left_ankle",
    "neck_pitch",
    "head_pitch",
    "head_yaw",
    "head_roll",
    "right_hip_yaw",
    "right_hip_roll",
    "right_hip_pitch",
    "right_knee",
    "right_ankle",
)

HOME = np.array(
    [0, -0.0873, -0.4579, -0.0049, 0.453, 0.3491, 0.3491, 0, 0, 0, 0.0873, 0.4579, 0.0049, -0.453],
    dtype=np.float32,
)


class Driver:
    def __init__(self, model, prefix, sessions):
        self.ids = np.array([model.actuator(prefix + name).id for name in POLICY_JOINTS])
        if len(self.ids) != 14:
            raise ValueError("官方模型应包含 14 个策略关节")
        self.q = model.jnt_qposadr[model.actuator_trnid[self.ids, 0]]
        self.v = model.jnt_dofadr[model.actuator_trnid[self.ids, 0]]
        self.root = model.jnt_qposadr[model.joint(prefix + "trunk_base_freejoint").id]
        self.body = model.body(prefix + "trunk_base").id
        self.gyro = model.sensor_adr[model.sensor(prefix + "imu_ang_vel").id]
        self.sessions = sessions
        self.command = np.zeros(13, dtype=np.float32)
        self.last = np.zeros(14, dtype=np.float32)
        self.policy = "walk"
        self.until = 0.0

    def step(self, model, data):
        if data.time >= self.until:
            self.policy = "walk"
        command = self.command if self.policy == "walk" else np.zeros(13)
        gravity = -data.xmat[self.body].reshape(3, 3)[2, :]
        obs = np.concatenate(
            [
                data.sensordata[self.gyro : self.gyro + 3],
                gravity,
                data.qpos[self.q] - HOME,
                data.qvel[self.v],
                self.last,
                command,
            ]
        ).astype(np.float32)
        session = self.sessions[self.policy]
        action = session.run(None, {session.get_inputs()[0].name: obs[None]})[0][0]
        if action.shape != (14,) or not np.isfinite(action).all():
            raise ValueError("策略返回无效关节目标")
        self.last[:] = action
        data.ctrl[self.ids] = HOME + action

    def pose(self, data):
        q = data.qpos[self.root + 3 : self.root + 7]
        yaw = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
        return data.qpos[self.root : self.root + 3].copy(), yaw


class MuJoCoBackend:
    kind = "mujoco"
    default_speed = 0.25

    def __init__(self, assets: Path):
        self.assets = assets
        self.robot_dir = assets / "microduck_rl/src/mjlab_microduck/robot/microduck"
        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        self.sessions = {
            key: ort.InferenceSession(
                str(assets / "policies" / file), options, providers=["CPUExecutionProvider"]
            )
            for key, file in {
                "walk": "velstand.onnx",
                "kick_left": "ball_kick_left.onnx",
                "kick_right": "ball_kick_right.onnx",
            }.items()
        }
        self.models = {scene: self._build(scene) for scene in ("ball", "duo", "carry")}
        # Geometry belongs to the compiled model, not to a reset of its dynamic state.
        self.revisions = {scene: uuid.uuid4().hex for scene in self.models}
        self.visual_cache = {}
        self.task = None
        self.error = None
        self.chorus = None
        self.selected = "a"
        self.load("ball")

    def _build(self, scene):
        if scene == "carry":
            return build_grasp_model(self.robot_dir)
        if scene == "ball":
            model = mujoco.MjModel.from_xml_path(str(self.robot_dir / "scene_ball.xml"))
        else:
            spec = mujoco.MjSpec.from_string(
                '<mujoco><worldbody><geom name="floor" type="plane" size="4 4 .1" '
                'rgba=".83 .87 .78 1"/></worldbody></mujoco>'
            )
            for prefix in ("a_", "b_"):
                robot = mujoco.MjSpec.from_file(str(self.robot_dir / "robot_allcollisions.xml"))
                spec.attach(robot, prefix=prefix, frame=spec.worldbody.add_frame())
            model = spec.compile()
        model.opt.timestep = 0.005
        return model

    def load(self, scene):
        self.scene = scene
        self.model = self.models[scene]
        self.data = mujoco.MjData(self.model)
        self.revision = self.revisions[scene]
        self.drivers = [
            Driver(self.model, p, self.sessions) for p in ([""] if scene != "duo" else ["a_", "b_"])
        ]
        for i, driver in enumerate(self.drivers):
            self.data.qpos[driver.root : driver.root + 7] = (
                [0, 0, 0.125, 1, 0, 0, 0]
                if scene != "duo"
                else [-0.25, 0, 0.125, 1, 0, 0, 0]
                if i == 0
                else [0.25, 0, 0.125, 0, 0, 0, 1]
            )
            self.data.qpos[driver.q] = HOME
            self.data.ctrl[driver.ids] = HOME
        self.grasp = BeakGrasp(self) if scene == "carry" else None
        self.selected = "a"
        self.chorus = None
        self.error = None
        self.contacts = {"ball": 0, "ducks": 0}
        self.ball_feet = set()
        self.ball_start = None
        self.discovered = []
        self.geom_ids = [
            i
            for i in range(self.model.ngeom)
            if self.model.geom_group[i] == 2 or self.model.geom(i).name == "ball_geom"
        ]
        self.geom_owner = []
        for i in range(self.model.ngeom):
            name = self.model.body(self.model.geom_bodyid[i]).name
            self.geom_owner.append(
                0 if name.startswith("a_") else 1 if name.startswith("b_") else -1
            )
        mujoco.mj_forward(self.model, self.data)
        # Explicit initial settling, not a simulated successful action.
        for _ in range(200 if scene == "carry" else 60):
            self.tick()
        self.wall_start = time.monotonic()
        self.sim_start = float(self.data.time)

    def tick(self):
        for driver in self.drivers:
            driver.step(self.model, self.data)
        ball = self.model.geom("ball_geom").id if self.scene == "ball" else -1
        for _ in range(4):
            previous_time = self.data.time
            mujoco.mj_step(self.model, self.data)
            if self.data.time <= previous_time or not np.isfinite(self.data.qpos).all():
                raise ValueError("MuJoCo 数值失稳，停止场景；请显式重置")
            if self.grasp:
                self.grasp.update()
            for contact in self.data.contact:
                one, two = int(contact.geom1), int(contact.geom2)
                if ball in (one, two) and ball >= 0:
                    other = two if one == ball else one
                    name = self.model.body(self.model.geom_bodyid[other]).name
                    if name in {"ankle_left", "ankle_right"}:
                        self.contacts["ball"] += 1
                        self.ball_feet.add(name.removeprefix("ankle_"))
                if {self.geom_owner[one], self.geom_owner[two]} == {0, 1}:
                    self.contacts["ducks"] += 1

    def start(self):
        if self.task is None or (self.task.done() and not self.error):
            self.task = asyncio.create_task(self._loop())

    async def _loop(self):
        try:
            while True:
                started = time.monotonic()
                self.tick()
                await asyncio.sleep(max(0.001, 0.02 - (time.monotonic() - started)))
        except asyncio.CancelledError:
            raise
        except Exception:
            self.error = "MuJoCo 推进失败，请重置场景"
            for driver in self.drivers:
                driver.command[:] = 0

    def targets(self):
        return (
            self.drivers
            if self.selected == "both"
            else [self.drivers[0 if self.selected == "a" else 1]]
        )

    def ensure_running(self):
        if self.error:
            raise ValueError(self.error)

    async def prepare(self, action):
        self.start()
        if self.error and action.name not in {
            "reset",
            "scene_ball",
            "scene_duo",
            "scene_carry",
            "stop",
        }:
            raise ValueError(self.error)
        if action.target != "a" and self.scene != "duo":
            raise ValueError("当前场景只有鸭 A")
        if self.grasp and action.name not in {
            "pick_up",
            "carry",
            "put_down",
            "stop",
            "reset",
            "scene_ball",
            "scene_duo",
            "scene_carry",
        }:
            raise ValueError("夹取场景请使用夹起、搬运、放下；其他动作会破坏夹持")
        self.selected = action.target

    async def move(self, vx, vyaw, vy=0):
        self.ensure_running()
        for driver in self.targets():
            driver.command[:3] = [vx, vy, vyaw]

    async def head(self, pitch, yaw=0, roll=0):
        self.ensure_running()
        for driver in self.targets():
            driver.command[4:7] = [pitch, yaw, roll]

    async def body_pose(self, z, roll, pitch, active):
        self.ensure_running()
        for driver in self.targets():
            driver.command[9:12] = [z, roll, pitch] if active else [0, 0, 0]

    async def stop(self):
        if self.grasp:
            self.grasp.stop()
        for driver in self.drivers:
            if self.grasp and self.grasp.held:
                driver.command[:3] = 0
                driver.command[7:] = 0
            else:
                driver.command[:] = 0
            driver.policy = "walk"
            driver.until = 0
        self.chorus = None

    async def reset(self):
        self.load(self.scene)
        if self.task and self.task.done():
            self.task = None
        self.start()

    def place_ball(self, foot):
        driver = self.drivers[0]
        position, yaw = driver.pose(self.data)
        lateral = 0.042 if foot == "left" else -0.042
        ball = self.model.joint("ball_free").id
        adr, vel = self.model.jnt_qposadr[ball], self.model.jnt_dofadr[ball]
        self.data.qpos[adr : adr + 7] = [
            position[0] + math.cos(yaw) * 0.09 - math.sin(yaw) * lateral,
            position[1] + math.sin(yaw) * 0.09 + math.cos(yaw) * lateral,
            0.035,
            1,
            0,
            0,
            0,
        ]
        self.data.qvel[vel : vel + 6] = 0
        self.ball_start = self.data.qpos[adr : adr + 3].copy()
        self.contacts["ball"] = 0
        self.ball_feet.clear()
        mujoco.mj_forward(self.model, self.data)

    def ball_state(self):
        if self.scene != "ball":
            return None
        pos = self.data.xpos[self.model.body("ball").id]
        distance = (
            float(np.linalg.norm(pos[:2] - self.ball_start[:2]))
            if self.ball_start is not None
            else 0
        )
        return {
            "position": pos.tolist(),
            "displacement_m": distance,
            "contacts": self.contacts["ball"],
            "contact_feet": sorted(self.ball_feet),
        }

    def discover(self):
        found = []
        if len(self.drivers) != 2:
            return found
        for i, driver in enumerate(self.drivers):
            other = self.drivers[1 - i]
            pos, yaw = driver.pose(self.data)
            dest, _ = other.pose(self.data)
            delta = dest - pos
            distance = float(np.linalg.norm(delta[:2]))
            bearing = math.atan2(delta[1], delta[0]) - yaw
            angle = math.atan2(math.sin(bearing), math.cos(bearing))
            if distance > 1.2 or abs(angle) > math.pi / 3:
                continue
            # Ray from just ahead of the trunk; own duck's geoms are excluded by group.
            groups = self.model.geom_group.copy()
            try:
                for g, owner in enumerate(self.geom_owner):
                    self.model.geom_group[g] = 5 if owner == i else 0
                direction = delta / np.linalg.norm(delta)
                hit = np.array([-1], dtype=np.int32)
                ray_distance = mujoco.mj_ray(
                    self.model,
                    self.data,
                    pos,
                    direction,
                    np.array([1, 0, 0, 0, 0, 0], dtype=np.uint8),
                    1,
                    -1,
                    hit,
                )
                visible = ray_distance >= 0 and self.geom_owner[hit[0]] == 1 - i
            finally:
                self.model.geom_group[:] = groups
            if visible:
                found.append(
                    {
                        "observer": "ab"[i],
                        "peer": "ab"[1 - i],
                        "distance_m": distance,
                        "bearing_rad": angle,
                    }
                )
        return found

    async def perform(self, action):
        if action.name.startswith("scene_"):
            self.load(action.name.removeprefix("scene_"))
            self.start()
            return {"scene": self.scene, "verified": True}
        if action.name in {"pick_up", "carry", "put_down"}:
            if not self.grasp:
                raise ValueError("请先切换到嘴部搬运场景")
            return await self.grasp.perform(action.name)
        if action.name.startswith("kick_"):
            if self.scene != "ball" or action.target != "a":
                raise ValueError("请先切换到单鸭踢球场景，选择鸭 A")
            foot = action.name.removeprefix("kick_")
            self.place_ball(foot)
            driver = self.drivers[0]
            driver.policy, driver.until = action.name, float(self.data.time) + 0.5
            await self.wait_sim(2)
            result = self.ball_state()
            verified = foot in self.ball_feet and result["displacement_m"] > 0.02
            return {
                **result,
                "foot": foot,
                "verified": verified,
                "message": "已确认脚球接触及球位移"
                if verified
                else "未确认所选脚踢中球，请重置后重试",
            }
        if self.scene != "duo":
            raise ValueError("请先切换到双鸭互动场景")
        if action.name == "find_companion":
            self.discovered = self.discover()
            for result in self.discovered:
                self.drivers["ab".index(result["observer"])].command[5] = result["bearing_rad"]
            await self.wait_sim(0.6)
            return {
                "peers": self.discovered,
                "sensor": "ground_truth_fov_raycast",
                "verified": bool(self.discovered),
                "message": "已发现同伴" if self.discovered else "视野内没有发现同伴",
            }
        if action.name in {"duo_walk", "collide"}:
            before = self.contacts["ducks"]
            for driver in self.drivers:
                driver.command[0] = 0.25
            await self.wait_sim(action.duration)
            contacts = self.contacts["ducks"] - before
            return {
                "contact_samples": contacts,
                "verified": contacts > 0 if action.name == "collide" else True,
                "message": "发生双鸭接触" if contacts else "本轮未发生双鸭接触，请重置场景后重试",
            }
        if action.name == "chorus":
            self.chorus = {
                "id": action.request_id,
                "started": time.monotonic(),
                "duration": 3,
                "tempo": 120,
                "source": "local_synth",
                "parts": 2,
            }
            start = time.monotonic()
            while (elapsed := time.monotonic() - start) < 3:
                self.ensure_running()
                for driver in self.drivers:
                    driver.command[4] = 0.10 * math.sin(elapsed * math.tau * 2)
                await asyncio.sleep(0.02)
            return {
                "verified": True,
                "parts": 2,
                "source": "local_synth",
                "audio_delivery": "browser_requires_audio_enabled",
            }
        raise ValueError("不支持的场景动作")

    async def wait_sim(self, duration):
        until, deadline = self.data.time + duration, time.monotonic() + duration + 3
        while self.data.time < until:
            if self.error or time.monotonic() > deadline:
                raise ValueError(self.error or "仿真推进超时，动作已停止")
            await asyncio.sleep(0.02)

    def geometry(self):
        if self.scene in self.visual_cache:
            return {"revision": self.revision, **self.visual_cache[self.scene]}
        self.visual_cache[self.scene] = geometry(self.model, self.geom_ids)
        return {"revision": self.revision, **self.visual_cache[self.scene]}

    async def snapshot(self):
        self.start()
        elapsed = time.monotonic() - self.wall_start
        chorus = None
        if self.chorus:
            chorus = {k: v for k, v in self.chorus.items() if k != "started"}
            chorus["elapsed"] = time.monotonic() - self.chorus["started"]
        return {
            "kind": self.kind,
            "connected": not self.error,
            "physics": True,
            "runtime": "mujoco_cpu_onnx",
            "scene": self.scene,
            "revision": self.revision,
            "pose": {},
            "velocity": {"forward": float(self.drivers[0].command[0])},
            "sim_time": float(self.data.time),
            "real_time_factor": (float(self.data.time) - self.sim_start) / max(elapsed, 0.001),
            "ducks": [
                {
                    "id": "ab"[i],
                    "position": d.pose(self.data)[0].tolist(),
                    "yaw": d.pose(self.data)[1],
                    "policy": d.policy,
                    "fallen": bool(self.data.xmat[d.body].reshape(3, 3)[2, 2] < 0.45),
                }
                for i, d in enumerate(self.drivers)
            ],
            "ball": self.ball_state(),
            "grasp": self.grasp.snapshot() if self.grasp else None,
            "contacts": dict(self.contacts),
            "discovered": self.discovered,
            "chorus": chorus,
            "error": self.error,
            "geoms": [
                {
                    "id": i,
                    "position": self.data.geom_xpos[i].tolist(),
                    "rotation": self.data.geom_xmat[i].tolist(),
                }
                for i in self.geom_ids
            ],
        }

    async def close(self):
        await self.stop()
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
