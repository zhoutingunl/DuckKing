"""One workbench session with the original, independently calibrated policies."""

import logging
from collections import Counter

from .feature_catalog import WORKBENCH_ACTIONS, WORKBENCH_GROUPS
from .feature_lifecycle import start_plan
from .feature_worlds import ExistingWorld, TaskMuJoCoBackend
from .local_commands import BOUNDED_DURATION
from .motion import MotionController


class WorkbenchSkills(ExistingWorld):
    def __init__(self, assets):
        self.capability = "movement"
        self.backend = TaskMuJoCoBackend(assets, skills_only=True)
        self.motion = MotionController(self.backend)
        self.metrics = {}
        self.idle_requested = False

    async def perform(self, command):
        timing = {"duration": command.duration} if command.action in BOUNDED_DURATION else {}
        outcome = await self.action(command.action, **timing)
        if command.action in {"idle_on", "idle_off"}:
            self.idle_requested = command.action == "idle_on"
        upright = not (await self.backend.snapshot())["ducks"][0]["fallen"]
        return {
            **outcome,
            "verified": upright and outcome.get("verified", True),
            "message": outcome.get("message", "动作已完成") if upright else "身体失稳，未完成动作",
        }

    async def finish(self):
        if self.idle_requested:
            self.backend.idle.enabled = True
            self.backend.start()
        else:
            await self.stop()


class WorkbenchWorld:
    def __init__(self, assets, make_world):
        self.worlds = {"movement": WorkbenchSkills(assets)}
        self.active = "movement"
        self.trials = set()
        self.states = {}
        for capability in WORKBENCH_GROUPS:
            if capability == "movement":
                continue
            try:
                self.worlds[capability] = make_world(assets, capability)
            except Exception:
                logging.getLogger(__name__).exception(
                    "workbench_policy_unavailable: %s", capability
                )
        self.visual, self.geom_ids = self.collect_geometry()

    @property
    def world(self):
        return self.worlds[self.active]

    @property
    def metrics(self):
        return self.world.metrics

    @metrics.setter
    def metrics(self, value):
        self.world.metrics = value

    def collect_geometry(self):
        # Instances with identical appearance can share an ID across policies,
        # but each instance in the same physical model needs its own transform.
        meshes, geoms, mesh_ids, geom_keys, ids = {}, [], {}, {}, {}
        for capability, world in self.worlds.items():
            model = world.geometry()
            mapped_meshes = {}
            for key, mesh in model["meshes"].items():
                signature = (mesh["vertices"], mesh["faces"])
                index = mesh_ids.setdefault(signature, len(mesh_ids))
                meshes[index] = mesh
                mapped_meshes[int(key)] = index
            occurrences = Counter()
            mapping = ids[capability] = {}
            for geom in model["geoms"]:
                mesh = mapped_meshes[geom["mesh"]] if geom["type"] == 7 else -1
                signature = (
                    geom["type"], mesh, tuple(geom["size"]), tuple(geom["rgba"]),
                    geom["duck"], geom["part"],
                )
                instance = signature, occurrences[signature]
                occurrences[signature] += 1
                index = geom_keys.setdefault(instance, len(geom_keys))
                if index == len(geoms):
                    geoms.append({**geom, "id": index, "mesh": mesh})
                mapping[geom["id"]] = index
        return {
            "meshes": meshes,
            "geoms": geoms,
            "dynamic_geometry": True,
            "attribution": "Pollen Robotics · CC BY-NC-SA 4.0 models",
        }, ids

    def geometry(self):
        return self.visual

    async def snapshot(self):
        state = self.states[self.active] = await self.world.snapshot()
        ids = self.geom_ids[self.active]
        x, y, _ = state["ducks"][0]["position"]
        return {
            **state,
            "workbench_policy": self.active,
            "camera_follow": state.get("camera_follow", [x, y, 0.125]),
            "geoms": [
                {**geom, "id": ids[geom["id"]]} for geom in state["geoms"] if geom["id"] in ids
            ],
        }

    def plan(self, state, action):
        target = WORKBENCH_ACTIONS[action]
        if target not in self.worlds:
            return {"mode": "blocked", "reason": "该动作的物理策略暂不可用。"}
        return start_plan(
            self.worlds[target],
            target,
            {"status": "completed" if target in self.trials else "idle"},
            state if target == self.active else self.states.get(target, {}),
            action,
        )

    def activate(self, action):
        self.active = WORKBENCH_ACTIONS[action]

    async def perform(self, command):
        self.trials.add(self.active)
        return await self.world.perform(command)

    async def finish(self):
        if self.active == "movement":
            await self.world.finish()
        else:
            await self.world.stop()

    async def stop(self, next_action=None):
        if self.active == "movement" and WORKBENCH_ACTIONS.get(next_action) != self.active:
            self.world.idle_requested = False
        await self.world.stop()
        self.states[self.active] = await self.world.snapshot()

    async def reset(self):
        await self.world.reset()
        self.trials.discard(self.active)

    async def close(self):
        for world in self.worlds.values():
            await world.close()
