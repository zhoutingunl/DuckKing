"""CPU MuJoCo scenes using Pollen's MJCF and ONNX policies, independently of robotd.

Observation layout, home pose and 50 Hz inference follow microduck_rl/infer_policy.py
(Apache-2.0, Pollen Robotics). Assets remain external; see THIRD_PARTY.md.
"""

import asyncio
import math
import secrets
import time
import uuid
from contextlib import suppress
from pathlib import Path

import mujoco
import numpy as np
import onnxruntime as ort

from .grasp import BeakGrasp
from .grasp_model import build_grasp_model
from .idle import IdleBehaviour
from .model_assets import geometry
from .motion_catalog import SKILL_DURATIONS, TRANSLATIONS
from .official_skills import perform_skill, perform_translation
from .posture import change_posture, measure_posture
from .seated_choir import SEATED_SPAWNS, SeatedChoir
from .skills_model import build_skills_model
from .stage import FloorStage, build_stage_model, scatter
from .table_choir import SPAWNS, TABLE_HEIGHT, TableChoir, build_table_model

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
    def __init__(self, model, prefix, sessions, base_policy="walk"):
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
        self.base_policy = self.policy = base_policy
        self.phase_started = 0.0
        self.until = 0.0
        self.posture_target = self.rest_posture = "stand"
        bodies = {self.body}
        for i in range(self.body + 1, model.nbody):
            if int(model.body_parentid[i]) in bodies:
                bodies.add(i)
        self.contact_geoms = {i for i in range(model.ngeom) if model.geom_bodyid[i] in bodies}

    def step(self, model, data):
        if self.policy not in {"sitstand", self.base_policy} and data.time >= self.until:
            self.policy = self.base_policy
        command = self.command.copy() if self.policy == self.base_policy else np.zeros(13)
        if self.policy in {"ground_pick", "roller_crouch"}:
            period = 4 if self.policy == "ground_pick" else 5
            phase = (data.time - self.phase_started) / period * math.tau
            command[:2] = [math.cos(phase), math.sin(phase)]
        if self.policy == "sitstand":
            # vx is a binary posture flag here, never a walking velocity.
            command[0] = float(self.posture_target == "sit")
            command[3:7] = self.command[3:7]
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
        # Keep previous_action in the network's units. Scale only the joint targets;
        # the roll needs its own calibrated gain for reliable full rotation/recovery.
        scale = 0.8 if self.base_policy == "roller" else 0.9 if self.policy == "roulade" else 1
        data.ctrl[self.ids] = HOME + action * scale

    def pose(self, data):
        q = data.qpos[self.root + 3 : self.root + 7]
        yaw = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
        return data.qpos[self.root : self.root + 3].copy(), yaw


class MuJoCoBackend:
    kind = "mujoco"
    default_speed = 0.25

    def __init__(self, assets: Path):
        self.assets = assets
        self.table_build_task = None
        self.stage_build_task = None
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
                "sitstand": "alpha_sitstand.onnx",
                "roulade": "roulade.onnx",
                "ground_pick": "alpha_ground_pick.onnx",
                "roller": "roller.onnx",
                "roller_crouch": "roller_crouch.onnx",
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
        if scene in {"skills", "rollers"}:
            return build_skills_model(self.robot_dir, rollers=scene == "rollers")
        if scene == "stage":
            return build_stage_model(self.robot_dir)
        if scene == "table":
            return build_table_model(self.robot_dir)
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
        if scene in {"skills", "rollers", "stage"} and scene not in self.models:
            self.models[scene] = self._build(scene)
            self.revisions[scene] = uuid.uuid4().hex
        if scene in {"table", "seated"} and scene not in self.models:
            if "table" not in self.models:
                self.models["table"] = self._build("table")
                self.revisions["table"] = uuid.uuid4().hex
            self.models[scene] = self.models["table"]
            self.revisions[scene] = self.revisions["table"]
        self.scene = scene
        self.model = self.models[scene]
        self.data = mujoco.MjData(self.model)
        self.revision = self.revisions[scene]
        prefixes = (
            [c + "_" for c in "abcd"]
            if scene in {"table", "seated", "stage"}
            else ["a_", "b_"]
            if scene == "duo"
            else [""]
        )
        self.drivers = [
            Driver(self.model, p, self.sessions, "roller" if scene == "rollers" else "walk")
            for p in prefixes
        ]
        stage_seed = secrets.randbelow(2**31)
        stage_spawns = scatter(stage_seed) if scene == "stage" else []
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
            if scene == "rollers":
                self.data.qpos[driver.root + 2] = 0.1385
            if scene in {"table", "seated"}:
                self.data.qpos[driver.root : driver.root + 7] = [
                    *(SEATED_SPAWNS[i] if scene == "seated" else SPAWNS[i]),
                    TABLE_HEIGHT + 0.125,
                    1,
                    0,
                    0,
                    0,
                ]
            if scene == "stage":
                x, y, yaw = stage_spawns[i]
                self.data.qpos[driver.root : driver.root + 7] = [
                    x,
                    y,
                    0.125,
                    math.cos(yaw / 2),
                    0,
                    0,
                    math.sin(yaw / 2),
                ]
        self.grasp = BeakGrasp(self) if scene == "carry" else None
        self.selected = "a"
        self.chorus = None
        self.error = None
        self.contacts = {"ball": 0, "ducks": 0}
        self.ball_feet = set()
        self.ball_start = None
        self.ball_prepared = None
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
                next((j for j, c in enumerate("abcd") if name.startswith(c + "_")), -1)
            )
        self.tabletop = TableChoir(self) if scene == "table" else None
        self.seated = SeatedChoir(self) if scene == "seated" else None
        self.idle = IdleBehaviour(self) if scene == "skills" else None
        self.skill_run = None
        self.stage = FloorStage(self, stage_seed) if scene == "stage" else None
        mujoco.mj_forward(self.model, self.data)
        # Explicit initial settling, not a simulated successful action.
        for _ in range(200 if scene == "carry" else 60):
            self.tick()
        self.wall_start = time.monotonic()
        self.sim_start = float(self.data.time)

    def tick(self):
        if self.idle:
            self.idle.tick()
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
            if self.tabletop:
                self.tabletop.update()
            if self.seated:
                self.seated.update()
            if self.stage:
                self.stage.update_contacts()
            for contact in self.data.contact:
                one, two = int(contact.geom1), int(contact.geom2)
                if ball in (one, two) and ball >= 0:
                    other = two if one == ball else one
                    name = self.model.body(self.model.geom_bodyid[other]).name
                    if name in {"ankle_left", "ankle_right"}:
                        self.contacts["ball"] += 1
                        self.ball_feet.add(name.removeprefix("ankle_"))
                if (
                    self.geom_owner[one] >= 0
                    and self.geom_owner[two] >= 0
                    and self.geom_owner[one] != self.geom_owner[two]
                ):
                    self.contacts["ducks"] += 1
        if self.skill_run:
            self.skill_run.tick()

    def start(self):
        if self.task is None or (self.task.done() and not self.error):
            self.task = asyncio.create_task(self._loop())

    async def _loop(self):
        try:
            next_tick = time.monotonic()
            while True:
                self.tick()
                # Keep a shared wall-clock cadence instead of accumulating event-loop
                # scheduling jitter on every frame. Catch up with real physics steps,
                # yielding after each one; never accumulate more than three steps.
                next_tick += 0.02
                now = time.monotonic()
                next_tick = max(next_tick, now - 0.06)
                await asyncio.sleep(max(0.001, next_tick - now))
        except asyncio.CancelledError:
            raise
        except Exception:
            self.error = "MuJoCo 推进失败，请重置场景"
            if self.idle:
                self.idle.enabled = False
                self.idle.stop()
            for driver in self.drivers:
                driver.command[:] = 0

    def targets(self):
        return (
            self.drivers if self.selected == "both" else [self.drivers["abcd".index(self.selected)]]
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
            "scene_table",
            "scene_seated",
            "scene_skills",
            "scene_rollers",
            "scene_stage",
            "stop",
        }:
            raise ValueError(self.error)
        if action.target != "a" and self.scene not in {"duo", "table", "seated", "stage"}:
            raise ValueError("当前场景只有鸭 A")
        if self.stage and not (
            action.name.startswith("stage_")
            or action.name.startswith("scene_")
            or action.name in {"stop", "reset"}
        ):
            raise ValueError("四鸭发布会请使用集结、点名翻滚和齐舞工具")
        if self.grasp and action.name not in {
            "pick_up",
            "carry",
            "put_down",
            "stop",
            "reset",
            "scene_ball",
            "scene_duo",
            "scene_carry",
            "scene_table",
            "scene_seated",
            "scene_skills",
            "scene_rollers",
            "scene_stage",
        }:
            raise ValueError("夹取场景请使用夹起、搬运、放下；其他动作会破坏夹持")
        if self.tabletop and action.name not in {
            "table_show",
            "stop",
            "reset",
            "scene_ball",
            "scene_duo",
            "scene_carry",
            "scene_table",
            "scene_seated",
            "scene_skills",
            "scene_rollers",
            "scene_stage",
        }:
            raise ValueError("桌上场景请使用完整合唱表演，避免单独行走破坏舞台布置")
        if self.seated and action.name not in {
            "seated_ready", "seated_solo",
            "seated_show",
            "stop",
            "reset",
            "scene_ball",
            "scene_duo",
            "scene_carry",
            "scene_table",
            "scene_seated",
            "scene_skills",
            "scene_rollers",
            "scene_stage",
        }:
            raise ValueError("坐姿合唱舞台请使用完整轮唱节目")
        self.selected = action.target
        if self.stage and action.name.startswith("stage_"):
            return
        if self.idle:
            if action.name in {"stop", "reset"} or action.name.startswith("scene_"):
                self.idle.enabled = False
            self.idle.pause()
        if (
            self.scene == "rollers"
            and not action.name.startswith("scene_")
            and action.name
            not in {
                "skate",
                "roller_crouch",
                "stop",
                "reset",
                "nod",
                "shake_head",
                "tilt_head",
            }
        ):
            raise ValueError("轮滑场景请使用滑行、轮滑下蹲或头部动作；其他动作需切换场景")
        if action.name not in {
            "sit",
            "stand",
            "nod",
            "shake_head",
            "tilt_head", "look_left", "look_right", "look_forward", "look_down",
            "idle_on",
            "idle_off",
            "yawn",
            "stop",
            "reset",
            "chorus",
            "find_companion",
            "seated_show", "seated_ready", "seated_solo",
        } and not action.name.startswith("scene_"):
            drivers = self.drivers if action.name in {"duo_walk", "collide"} else self.targets()
            if any(d.rest_posture == "sit" for d in drivers):
                raise ValueError("请先让小鸭站起来，再执行行走、转向或踢球")
            for d in drivers:
                if d.policy == "sitstand" and not action.name.startswith("kick_"):
                    d.policy = "walk"

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
        if self.stage:
            self.stage.stop()
        if self.tabletop:
            self.tabletop.stop()
        if self.seated:
            self.seated.stop()
        if self.grasp:
            self.grasp.stop()
        for driver in self.drivers:
            if self.grasp and self.grasp.held:
                driver.command[:3] = 0
                driver.command[7:] = 0
            else:
                driver.command[:] = 0
            if driver.policy == "sitstand":
                driver.posture_target = driver.rest_posture
            else:
                driver.policy = driver.base_policy
            driver.until = 0
        if self.idle:
            self.idle.stop()
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

    def ball_observation(self):
        if self.scene != "ball":
            raise ValueError("当前不是踢球舞台")
        driver = self.drivers[0]
        position, yaw = driver.pose(self.data)
        ball = self.data.xpos[self.model.body("ball").id]
        dx, dy = ball[:2] - position[:2]
        forward = math.cos(yaw) * dx + math.sin(yaw) * dy
        lateral = -math.sin(yaw) * dx + math.cos(yaw) * dy
        ready = {foot: bool(abs(forward - .09) < .035 and abs(lateral - side) < .03
                            and .025 < ball[2] < .05 and driver.rest_posture == "stand")
                 for foot, side in (("left", .042), ("right", -.042))}
        return {"sensor": "mujoco_state_query", "ball": self.ball_state(), "ready": ready,
                "prepared_foot": self.ball_prepared,
                "message": "只读取仿真状态，本次没有摆球或踢球"}

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
        if action.name in TRANSLATIONS:
            return await perform_translation(self, action)
        if action.name in SKILL_DURATIONS:
            return await perform_skill(self, action)
        if action.name.startswith("scene_"):
            if action.name in {"scene_table", "scene_seated"} and "table" not in self.models:
                # Cancelling a UI request cannot stop native compilation. Keep
                # one pending build so rapid replacements never launch several
                # four-robot compilers or switch scenes after cancellation.
                if self.table_build_task is None:
                    self.table_build_task = asyncio.create_task(
                        asyncio.to_thread(self._build, "table")
                    )
                    self.table_build_task.add_done_callback(
                        lambda task: None if task.cancelled() else task.exception()
                    )
                try:
                    self.models["table"] = await asyncio.shield(self.table_build_task)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.table_build_task = None
                    raise
                self.table_build_task = None
                self.revisions["table"] = uuid.uuid4().hex
            if action.name == "scene_stage" and "stage" not in self.models:
                if self.stage_build_task is None:
                    self.stage_build_task = asyncio.create_task(
                        asyncio.to_thread(self._build, "stage"))
                    self.stage_build_task.add_done_callback(
                        lambda task: None if task.cancelled() else task.exception())
                try:
                    self.models["stage"] = await asyncio.shield(self.stage_build_task)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.stage_build_task = None
                    raise
                self.stage_build_task = None
                self.revisions["stage"] = uuid.uuid4().hex
            self.load(action.name.removeprefix("scene_"))
            self.start()
            return {"scene": self.scene, "verified": True}
        if action.name.startswith("stage_"):
            if not self.stage:
                raise ValueError("请先准备四鸭发布会舞台")
            operation = action.name.removeprefix("stage_")
            if operation == "roll":
                members = action.members or self.stage.members(action.member)
                return await self.stage.perform(operation, members)
            member = self.stage.member(action.member) if operation == "poke" else "a"
            return await self.stage.perform(operation, member)
        if action.name in {"sit", "stand"}:
            return await change_posture(self, self.targets(), action.name, action.duration)
        if action.name in {"seated_ready", "seated_solo"}:
            if not self.seated:
                raise ValueError("请先切换到坐姿合唱舞台")
            if action.name == "seated_ready":
                return await change_posture(self, self.drivers, "sit")
            return await self.seated.single(action.target)
        if action.name == "seated_show":
            if not self.seated:
                raise ValueError("请先切换到坐姿合唱舞台")
            return await self.seated.perform()
        if action.name == "table_show":
            if not self.tabletop:
                raise ValueError("请先切换到桌上合唱场景")
            return await self.tabletop.perform()
        if action.name in {"pick_up", "carry", "put_down"}:
            if not self.grasp:
                raise ValueError("请先切换到嘴部搬运场景")
            return await self.grasp.perform(action.name)
        if action.name.startswith("ball_prepare_"):
            if self.scene != "ball":
                raise ValueError("请先切到踢球舞台")
            foot = action.name.removeprefix("ball_prepare_")
            driver = self.drivers[0]
            driver.policy = driver.base_policy
            driver.command[:] = 0
            await self.wait_sim(0.4)
            self.place_ball(foot)
            self.ball_prepared = foot
            await self.wait_sim(0.2)
            return {
                "verified": True,
                "message": "已明确摆球，尚未踢球",
                "foot": foot,
                **self.ball_observation(),
            }
        if action.name.startswith("ball_shoot_"):
            foot = action.name.removeprefix("ball_shoot_")
            state = self.ball_observation()
            if self.ball_prepared != foot or not state["ready"].get(foot):
                raise ValueError("球尚未在所选脚前准备好，请明确摆球后再踢；未移动球")
            self.ball_prepared = None
            self.contacts["ball"] = 0
            self.ball_feet.clear()
            self.ball_start = self.data.xpos[self.model.body("ball").id].copy()
            driver = self.drivers[0]
            driver.policy, driver.until = "kick_" + foot, float(self.data.time) + 0.5
            await self.wait_sim(2)
            result = self.ball_state()
            verified = foot in self.ball_feet and result["displacement_m"] > 0.02
            return {
                **result,
                "foot": foot,
                "verified": verified,
                "message": "已确认所选脚触球和位移" if verified else "本轮未确认踢中",
            }
        if action.name.startswith("kick_"):
            if self.scene != "ball" or action.target != "a":
                raise ValueError("请先切换到单鸭踢球场景，选择鸭 A")
            foot = action.name.removeprefix("kick_")
            driver = self.drivers[0]
            # Sitstand finishes with nearly straight knees; the kick policy was
            # trained from the walking stance. Let that policy establish its pose
            # before placing the ball. Keep the entire action within two sim seconds.
            settle = 0.4 if driver.policy == "sitstand" else 0.0
            if settle:
                driver.policy = driver.base_policy
                driver.command[:] = 0
                await self.wait_sim(settle)
            self.place_ball(foot)
            driver.policy, driver.until = action.name, float(self.data.time) + 0.5
            await self.wait_sim(action.duration - settle)
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
                    "id": "abcd"[i],
                    "position": d.pose(self.data)[0].tolist(),
                    "yaw": d.pose(self.data)[1],
                    "policy": d.policy,
                    "posture": measure_posture(self, d)
                    if self.scene in {"ball", "duo", "seated", "skills", "stage"}
                    else None,
                    "fallen": bool(self.data.xmat[d.body].reshape(3, 3)[2, 2] < 0.45),
                }
                for i, d in enumerate(self.drivers)
            ],
            "ball": self.ball_state(),
            "grasp": self.grasp.snapshot() if self.grasp else None,
            "tabletop": self.tabletop.snapshot() if self.tabletop else None,
            "seated_choir": self.seated.snapshot() if self.seated else None,
            "idle": self.idle.snapshot() if self.idle else None,
            "stage": self.stage.snapshot() if self.stage else None,
            "owners": {
                str(i): "abcd"[owner] for i, owner in enumerate(self.geom_owner) if owner >= 0
            }
            if self.stage
            else {},
            "skill": self.skill_run.snapshot() if self.skill_run else None,
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
        if self.idle:
            self.idle.enabled = False
        await self.stop()
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
