"""Three physical ducks and a contact-enabled rope, replaying community policies.

The upstream synchronous rehearsal runs on one owned thread. Only immutable
snapshots cross threads. Cancellation is checked every physics step; reset
joins the old world before creating a new one. Success uses PhysicalSkipAudit,
never the upstream legacy timing-only counter.
"""

import asyncio
import functools
import math
import os
import sys
import threading
import time
import traceback

import mujoco
import onnxruntime as ort
from scipy.spatial import ConvexHull, QhullError

from .feature_source import compatible_module
from .model_assets import geometry


class RehearsalCancelled(Exception):
    pass


class CircusWorld:
    def __init__(self, assets):
        root = assets / "features/circus"
        os.environ["MICRODUCK_ROOT"] = str(assets)
        sys.path.insert(0, str(root / "src"))
        compatible_module(root / "src/microduck_lab/sim/composer.py", "microduck_lab.sim.composer")
        classic = compatible_module(
            root / "src/microduck_lab/sim/classic_rope.py", "microduck_lab.sim.classic_rope"
        )
        classic.build_classic_world = functools.partial(
            classic.build_classic_world,
            robot_xml=str(
                assets
                / "features/upstream/src/mjlab_microduck/robot/microduck/robot_allcollisions.xml"
            ),
        )
        from microduck_lab.demos import honest_skip
        from microduck_lab.sim.runtime import PolicyBank
        from microduck_lab.sim.skip_metrics import PhysicalSkipAudit

        def cpu_session(bank, name):
            if name not in bank._sessions:
                options = ort.SessionOptions()
                options.intra_op_num_threads = options.inter_op_num_threads = 1
                bank._sessions[name] = ort.InferenceSession(
                    bank.paths[name], options, providers=["CPUExecutionProvider"]
                )
            return bank._sessions[name]

        PolicyBank.get = cpu_session

        class HullAudit(PhysicalSkipAudit):
            def setup(self, model, data, info):
                super().setup(model, data, info)
                # Linear extrema of a mesh equal its convex hull's extrema.
                # Keep the exact per-physics-step test, avoiding millions of
                # redundant interior vertices; never reduce contact sampling.
                for geom, vertices in self.vertices.items():
                    try:
                        self.vertices[geom] = vertices[ConvexHull(vertices).vertices]
                    except QhullError:
                        pass  # Degenerate meshes retain their complete vertices.

        self.audit_class = HullAudit
        self.rehearsal = honest_skip.run_honest_classic_skip
        honest_skip.POL = assets / "features/policies/circus-base"
        self.root = root
        self.thread = None
        self.start_thread()

    def start_thread(self):
        self.ready, self.begin, self.cancelled, self.done = (threading.Event() for _ in range(4))
        self.error = None
        self.metrics = {}
        self.state, self.visual, self.result = None, None, None
        self.thread = threading.Thread(target=self.run, name="duckking-circus", daemon=True)
        self.thread.start()
        if not self.ready.wait(60):
            self.cancelled.set()
            raise ValueError("跳绳物理模型准备超时")
        if self.error:
            raise ValueError(self.error)

    def run(self):
        audit = self.audit_class()
        published = [-1.0]
        clock = [None]

        def capture(model, data):
            geoms = [
                {
                    "id": i,
                    "position": data.geom_xpos[i].tolist(),
                    "rotation": data.geom_xmat[i].tolist(),
                }
                for i in self.ids
            ]
            ducks = []
            for name, id_ in zip(("lavender", "cream", "sky"), "abc", strict=True):
                body = model.body(name + "/trunk_base").id
                q = data.xquat[body]
                yaw = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
                ducks.append(
                    {
                        "id": id_,
                        "position": data.xpos[body].tolist(),
                        "yaw": yaw,
                        "fallen": bool(data.xmat[body].reshape(3, 3)[2, 2] < 0.3),
                    }
                )
            score = audit.scorer.result()
            self.metrics = {
                "sim_time": float(data.time),
                "clean_skips": score["clean_skips"],
                "full_revolutions": score["full_revolutions"],
                "physical_success_rate": score["physical_success_rate"],
                "real_time_factor": (
                    float(data.time) / max(0.01, time.monotonic() - clock[0])
                    if clock[0] is not None
                    else 0
                ),
            }
            self.state = {
                "physics": True,
                "runtime": "mujoco_cpu_onnx",
                "view_scene": "circus",
                "geoms": geoms,
                "ducks": ducks,
                "sim_time": float(data.time),
            }

        def setup(model, data, info):
            self.model, self.data = model, data
            model.opt.solver = mujoco.mjtSolver.mjSOL_NEWTON
            model.opt.integrator = mujoco.mjtIntegrator.mjINT_EULER
            audit.setup(model, data, info)
            self.ids = [
                i
                for i in range(model.ngeom)
                if model.geom_type[i] != mujoco.mjtGeom.mjGEOM_PLANE
                and (
                    model.geom_group[i] == 2
                    or model.geom(i).name.startswith(("rope/", "lavender/handle", "cream/handle"))
                )
            ]
            self.visual = geometry(model, self.ids)
            for geom in self.visual["geoms"]:
                name = model.body(int(model.geom_bodyid[geom["id"]])).name
                for prefix, duck in zip(("lavender/", "cream/", "sky/"), "abc", strict=True):
                    if name.startswith(prefix):
                        geom.update(duck=duck, part=geom["part"].removeprefix(prefix))

        def policy(model, data, info, runtime):
            if not self.ready.is_set():
                capture(model, data)
                self.ready.set()
            while not self.begin.wait(0.05):
                if self.cancelled.is_set():
                    raise RehearsalCancelled
            if clock[0] is None:
                clock[0] = time.monotonic() - data.time
            delay = clock[0] + data.time - time.monotonic()
            if delay > 0:
                self.cancelled.wait(min(0.02, delay))
            if self.cancelled.is_set():
                raise RehearsalCancelled

        def physics(model, data, info, hopping):
            if self.cancelled.is_set():
                raise RehearsalCancelled
            audit(model, data, info, hopping)
            if data.time - published[0] >= 0.05:
                capture(model, data)
                published[0] = data.time

        try:
            self.rehearsal(
                None,
                seconds=30,
                seed=0,
                render=False,
                turner_onnx=self.root / "policies/turner_rope.onnx",
                hop_onnx=self.root / "policies/ropehop_contact.onnx",
                rope_contacts="full",
                legacy_rope_offset=False,
                connect_timeconst=0.004,
                physics_dt=0.001,
                rope_length=0.58,
                jumper_y=0,
                rope_velocity_limit=40,
                model_setup=setup,
                policy_observer=policy,
                physics_observer=physics,
            )
            score = audit.scorer.result()
            self.result = {
                "verified": score["passed"],
                "message": "已完成真实接触评分"
                if score["passed"]
                else "本轮未通过完整跳绳验收；保留实际结果",
                **{k: v for k, v in score.items() if k != "cycles"},
            }
        except RehearsalCancelled:
            pass
        except Exception:
            traceback.print_exc()
            self.error = "跳绳物理实验未能继续，请重置后再试"
        finally:
            self.ready.set()
            self.done.set()

    async def perform(self, command):
        if self.done.is_set():
            raise ValueError("本轮已结束，请先重置再开始")
        self.begin.set()
        try:
            await asyncio.to_thread(self.done.wait)
            if self.error:
                raise ValueError(self.error)
            return self.result or {"verified": False, "message": "实验已停止"}
        finally:
            await self.stop()

    async def stop(self):
        if not self.begin.is_set() and not self.done.is_set():
            return
        await self.shutdown_thread()

    async def shutdown_thread(self):
        self.cancelled.set()
        await asyncio.to_thread(self.thread.join, 2)
        if self.thread.is_alive():
            raise ValueError("跳绳物理尚未停止，请释放场景")

    async def reset(self):
        await self.shutdown_thread()
        await asyncio.to_thread(self.start_thread)

    def geometry(self):
        return dict(self.visual)

    async def snapshot(self):
        return dict(self.state)

    async def close(self):
        await self.shutdown_thread()
