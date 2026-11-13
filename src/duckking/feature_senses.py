"""RGB-only visual servo, ray distance instrument, and explicitly mapped navigation.

The visual controller gets image pixels, never object IDs/positions or renderer
depth. Physics truth is used exclusively to score contact and report the result.
"""

import base64
import heapq
import math
import struct
import zlib

import mujoco
import numpy as np

from .feature_policies import PolicyWorld, session


def png_rgb(pixels):
    """Small bounded RGB PNG encoder; no imaging dependency in the server."""
    h, w, _ = pixels.shape

    def chunk(kind, payload):
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload))
        )

    rows = b"".join(b"\0" + row.tobytes() for row in pixels)
    return base64.b64encode(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 3))
        + chunk(b"IEND", b"")
    ).decode()


def largest_interior_blob(mask):
    """Run-length connected components; reject sky/edges and isolated color flecks."""
    h, w = mask.shape
    runs, parent, previous = [], [], []

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for y, row in enumerate(mask):
        edges = np.flatnonzero(np.diff(np.r_[False, row, False]))
        current = []
        for x0, x1 in zip(edges[::2], edges[1::2], strict=True):
            i = len(runs)
            runs.append((y, int(x0), int(x1)))
            parent.append(i)
            current.append(i)
            for j in previous:
                if runs[j][1] < x1 and runs[j][2] > x0:
                    parent[root(i)] = root(j)
        previous = current
    blobs = {}
    for i, (y, x0, x1) in enumerate(runs):
        b = blobs.setdefault(root(i), [0, 0.0, 0.0, False])
        n = x1 - x0
        b[0] += n
        b[1] += (x0 + x1 - 1) * n / 2
        b[2] += y * n
        b[3] |= x0 == 0 or x1 == w or y in {0, h - 1}
    candidates = [b for b in blobs.values() if 12 <= b[0] <= h * w * 0.3 and not b[3]]
    if not candidates:
        return None
    n, x, y, _ = max(candidates, key=lambda b: b[0])
    return {"x": x / n, "y": y / n, "area": n, "radius": math.sqrt(n / math.pi)}


def color_observation(pixels, color):
    rgb = pixels.astype(np.float32)
    channel = {"red": 0, "green": 1, "blue": 2, "yellow": 0}[color]
    own = rgb[:, :, channel]
    others = np.max(np.delete(rgb, channel, axis=2), axis=2)
    mask = (own > 70) & (own > others * 2.2)
    if color == "yellow":
        mask = (
            (rgb[:, :, 0] > 90)
            & (rgb[:, :, 1] > 80)
            & (rgb[:, :, 2] < np.minimum(rgb[:, :, 0], rgb[:, :, 1]) * 0.65)
        )
    return largest_interior_blob(mask)


def map_path(start, goal, obstacle=(0.38, -0.02, 0.10, 0.12)):
    """A* on a known 5 cm map, inflated by the duck's 12 cm footprint."""
    scale = 0.05
    a, b = tuple(round(float(x) / scale) for x in start), tuple(round(x / scale) for x in goal)
    queue, costs, parents = [(0, a)], {a: 0}, {}
    ox, oy, sx, sy = obstacle
    while queue:
        _, cell = heapq.heappop(queue)
        if cell == b:
            route = [cell]
            while route[-1] != a:
                route.append(parents[route[-1]])
            route.reverse()
            return [np.array(p) * scale for p in route]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = cell[0] + dx, cell[1] + dy
            x, y = nxt[0] * scale, nxt[1] * scale
            if abs(x) > 1.5 or abs(y) > 1.5:
                continue
            if abs(x - ox) < sx + 0.12 and abs(y - oy) < sy + 0.12:
                continue
            cost = costs[cell] + 1
            if cost >= costs.get(nxt, float("inf")):
                continue
            costs[nxt], parents[nxt] = cost, cell
            heapq.heappush(queue, (cost + abs(nxt[0] - b[0]) + abs(nxt[1] - b[1]), nxt))
    raise ValueError("地图中没有可通行路径")


def rgb_sphere_position(
    found,
    radius,
    camera_position,
    camera_rotation,
    body_position,
    body_rotation,
    focal=188.36161525409883,
):
    """Known-size monocular estimate in the robot frame; no simulator object pose."""
    depth = focal * radius / max(1, found["radius"])
    ray = np.array([(found["x"] - 160) / focal, (120 - found["y"]) / focal, -1])
    return body_rotation.T @ (camera_position + camera_rotation @ (depth * ray) - body_position)


class SensesWorld(PolicyWorld):
    def configure_spec(self, spec):
        for geom in spec.geoms:
            if geom.type == mujoco.mjtGeom.mjGEOM_PLANE:
                geom.material = ""
                geom.rgba = [0.88, 0.88, 0.84, 1]
        camera = next(c for c in spec.cameras if c.name == "head_camera")
        camera.fovy = 90 if self.capability == "soccer" else 65
        # MuJoCo cameras look down local -Z with local +Y up. The upstream
        # camera frame points into the shell; preserve its optical-centre site
        # but convert the CAD orientation to this renderer convention.
        camera.quat = [math.sqrt(0.5), 0, 0, -math.sqrt(0.5)]
        if self.capability == "navigation":
            spec.worldbody.add_geom(
                name="obstacle",
                type=mujoco.mjtGeom.mjGEOM_BOX,
                pos=[0.38, -0.02, 0.10],
                size=[0.10, 0.12, 0.10],
                rgba=[0.6, 0.48, 0.32, 1],
                group=2,
            )
            for name, pos, color in [
                ("door", [0.8, -0.35, 0.001], [0.2, 0.4, 0.8, 1]),
                ("home", [-0.25, 0.25, 0.001], [0.2, 0.6, 0.3, 1]),
                ("table", [0.8, 0.35, 0.001], [0.8, 0.3, 0.3, 1]),
            ]:
                spec.worldbody.add_geom(
                    name=name,
                    type=mujoco.mjtGeom.mjGEOM_CYLINDER,
                    pos=pos,
                    size=[0.09, 0.001, 0],
                    rgba=color,
                    group=2,
                    contype=0,
                    conaffinity=0,
                )
        elif self.capability == "soccer":
            body = spec.worldbody.add_body(name="feature_ball", pos=[0.22, 0.042, 0.035])
            body.add_freejoint(name="ball_free")
            body.add_geom(
                name="target_yellow",
                type=mujoco.mjtGeom.mjGEOM_SPHERE,
                size=[0.035, 0, 0],
                mass=0.035,
                rgba=[1, 0.85, 0.01, 1],
                group=2,
                condim=6,
                priority=2,
                friction=[0.7, 0.005, 0.002],
            )
        else:
            objects = [
                ("red", [0.6, 0, 0.16], [0.95, 0.04, 0.03, 1]),
                ("blue", [0.65, -0.28, 0.16], [0.02, 0.1, 0.95, 1]),
                ("green", [0.65, 0.28, 0.16], [0.02, 0.8, 0.08, 1]),
            ]
            for color, pos, rgba in objects:
                body = spec.worldbody.add_body(name="target_" + color, pos=pos, mocap=True)
                body.add_geom(
                    name="target_" + color,
                    type=mujoco.mjtGeom.mjGEOM_SPHERE,
                    size=[0.07, 0, 0],
                    rgba=rgba,
                    group=2,
                )
        return spec

    def __init__(self, assets, capability):
        super().__init__(assets, capability)
        self.renderer = mujoco.Renderer(self.model, height=240, width=320)
        self.render_option = mujoco.MjvOption()
        self.render_option.geomgroup[:] = [1, 0, 1, 0, 0, 0]
        self.sensors, self.image_tick = {}, -1
        self.sensor_frame()

    def sensor_frame(self):
        self.renderer.update_scene(self.data, camera="head_camera", scene_option=self.render_option)
        pixels = self.renderer.render().copy()
        camera = self.model.camera("head_camera").id
        origin = self.data.cam_xpos[camera].copy()
        orientation = self.data.cam_xmat[camera].reshape(3, 3)
        direction = -orientation[:, 2]
        raygroup = np.array([1, 0, 1, 0, 0, 0], dtype=np.uint8)
        hit = np.array([-1], dtype=np.int32)
        # The head camera is in front of its shell. The ray's origin shares the
        # optical axis so the distance visualization matches the displayed image.
        distance = mujoco.mj_ray(
            self.model,
            self.data,
            origin,
            direction,
            raygroup,
            True,
            int(self.model.cam_bodyid[camera]),
            hit,
        )
        distance = float(distance) if 0 <= distance <= 4 else None
        self.sensors = {
            "image": png_rgb(pixels),
            "mime": "image/png",
            "distance_m": distance,
            "sim_time": float(self.data.time),
        }
        if self.capability == "tof":
            depth = []
            # A virtual 45 x 45 degree scan, not a calibrated hardware emulator.
            tangent = math.tan(math.radians(22.5))
            for row in range(8):
                values = []
                for col in range(8):
                    ray = orientation @ np.array(
                        [(col / 7 * 2 - 1) * tangent, (1 - row / 7 * 2) * tangent, -1.0]
                    )
                    ray /= np.linalg.norm(ray)
                    length = mujoco.mj_ray(
                        self.model,
                        self.data,
                        origin,
                        ray,
                        raygroup,
                        True,
                        int(self.model.cam_bodyid[camera]),
                        hit,
                    )
                    values.append(float(length) if 0 <= length <= 4 else None)
                depth.append(values)
            self.sensors["depth_grid_m"] = depth
            self.sensors["scan_fov_deg"] = 45
        self.metrics["ray_distance_m"] = distance
        self.image_tick = self.data.time
        return pixels

    async def snapshot(self):
        state = await super().snapshot()
        if self.data.time - self.image_tick >= 0.18:
            self.sensor_frame()
        if self.capability == "navigation":
            state["view_scene"] = "navigation"
            state["annotations"] = [
                {
                    "id": name,
                    "text": title,
                    "position": (
                        self.data.geom_xpos[self.model.geom(name).id] + [0, 0, 0.07]
                    ).tolist(),
                }
                for name, title in (("door", "门口"), ("home", "窝旁"), ("table", "桌旁"))
            ]
        return {**state, "sensors": self.sensors, "feature_path": getattr(self, "route", [])}

    async def seek(self, color, *, kick=False):
        self.active_policy = self.walk
        self.command[:] = 0
        # Camera down-tilt is a head command, not a virtual camera relocation.
        self.command[4] = 1.0 if kick else 0.0
        await self.advance(0.5)
        focal = 120 / math.tan(math.radians(float(self.model.cam_fovy[0])) / 2)
        stable, misses = 0, 0
        for _ in range(180):
            found = color_observation(self.sensor_frame(), color)
            if found is None:
                stable = 0
                misses += 1
                self.command[:3] = [0, 0, 0.9 if misses < 80 else -0.9]
            else:
                radius = 0.035 if kick else 0.07
                estimate = focal * radius / max(1, found["radius"])
                bearing = math.atan2(160 - found["x"], focal)
                # Right/left foot alignment comes from image geometry only.
                if kick:
                    camera = self.model.camera("head_camera").id
                    position = rgb_sphere_position(
                        found,
                        radius,
                        self.data.cam_xpos[camera],
                        self.data.cam_xmat[camera].reshape(3, 3),
                        self.data.xpos[self.body],
                        self.data.xmat[self.body].reshape(3, 3),
                        focal=focal,
                    )
                    lateral = position[1] - self.kick_side * 0.042
                    close = position[0] < 0.095
                    self.metrics.update(
                        visual_ball_x_m=float(position[0]), visual_ball_y_m=float(position[1])
                    )
                else:
                    lateral = estimate * math.sin(bearing)
                    close = estimate < 0.32
                aligned = abs(lateral) < (0.009 if kick else 0.05)
                stable = stable + 1 if close and aligned else 0
                self.command[:3] = [
                    0 if close or (not kick and abs(bearing) > 0.18) else 0.3,
                    (float(np.sign(lateral) * 0.22) if abs(lateral) > 0.008 else 0) if kick else 0,
                    0 if kick or abs(bearing) < 0.08 else float(np.sign(bearing) * 0.9),
                ]
                self.metrics.update(rgb_area=found["area"], distance_m_to_target=estimate)
                if stable >= 3:
                    self.command[:3] = 0
                    await self.advance(0.6)
                    return True
            await self.advance(0.1)
        self.command[:3] = 0
        return False

    async def navigate(self, action):
        goal = {"go_door": [0.8, -0.35], "go_home": [-0.25, 0.25], "go_table": [0.8, 0.35]}[action]
        route = map_path(self.data.qpos[:2], goal)
        self.route = [p.tolist() for p in route]
        index = 1
        for _ in range(1500):
            position = self.data.qpos[:2]
            if np.linalg.norm(position - goal) < 0.07:
                self.command[:] = 0
                await self.advance(1)
                distance = float(np.linalg.norm(self.data.qpos[:2] - goal))
                self.metrics["distance_m_to_target"] = distance
                return {
                    "verified": distance < 0.09,
                    "message": "已按停下后的实际位置判定到达",
                    **self.metrics,
                }
            while index < len(route) - 1 and np.linalg.norm(position - route[index]) < 0.07:
                index += 1
            delta = route[min(index + 1, len(route) - 1)] - position
            q = self.data.qpos[3:7]
            yaw = math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2))
            desired = math.atan2(delta[1], delta[0])
            angle = math.atan2(math.sin(desired - yaw), math.cos(desired - yaw))
            self.command[:3] = [0.3 if abs(angle) < 0.35 else 0, 0, np.clip(angle * 2, -0.8, 0.8)]
            self.metrics["distance_m_to_target"] = float(np.linalg.norm(position - goal))
            await self.advance(0.02)
        return {
            "verified": False, "message": "规定时间内未到达，已暂停；可再次发出指令。",
            **self.metrics,
        }

    async def perform(self, command):
        self.metrics = {}
        if self.capability == "navigation":
            return await self.navigate(command.action)
        if self.capability == "search":
            color = command.action.removeprefix("find_")
            ok = await self.seek(color)
            # Truth only audits the final result; the controller above sees RGB.
            target = self.model.geom("target_" + color).id
            distance = float(
                np.linalg.norm((self.data.geom_xpos[target] - self.data.xpos[self.body])[:2])
            )
            self.metrics["distance_m_to_target"] = distance
            ok = ok and distance < 0.45
            return {
                "verified": ok,
                "message": "已从画面找到目标并走近停下" if ok else "未能从相机画面完成寻物",
                **self.metrics,
            }
        if self.capability == "soccer":
            self.kick_side = 1 if command.action == "kick_left" else -1
            found = await self.seek("yellow", kick=True)
            if not found:
                return {"verified": False, "message": "视觉找球或对齐未成功，没有执行踢球"}
            self.command[:] = 0
            await self.advance(0.8)
            self.active_policy = session(
                self.assets
                / "policies"
                / ("ball_kick_left.onnx" if self.kick_side == 1 else "ball_kick_right.onnx")
            )
            ball = self.model.geom("target_yellow").id
            start = self.data.geom_xpos[ball].copy()
            foot = self.foot_geoms[0 if self.kick_side == 1 else 1]
            contacts = [0]

            def contact():
                contacts[0] += sum(
                    ball in (c.geom1, c.geom2) and bool({int(c.geom1), int(c.geom2)} & foot)
                    for c in self.data.contact
                )

            await self.advance(0.5, contact)
            self.active_policy = self.walk
            await self.advance(1)
            distance = float(np.linalg.norm((self.data.geom_xpos[ball] - start)[:2]))
            self.metrics.update(foot_ball_contacts=contacts[0], distance_m=distance)
            return {
                "verified": contacts[0] > 0 and distance > 0.01,
                "message": "以实际脚球接触和球位移判定本轮结果",
                **self.metrics,
            }
        if self.capability == "theremin":
            self.command[:] = 0
            target = self.model.body("target_red").mocapid[0]
            initial = self.data.mocap_pos[target].copy()
            duration = 6 if command.action == "play" else 2
            for k in range(round(duration * 50)):
                if command.action == "play":
                    x = 0.55 + 0.22 * math.sin(k / 50 * math.tau / 3)
                else:
                    final = 0.32 if command.action == "near" else 0.85
                    x = initial[0] + (final - initial[0]) * (k + 1) / (duration * 50)
                self.data.mocap_pos[target, 0] = x
                await self.advance(0.02)
                if k % 10 == 0:
                    self.sensor_frame()
                    distance = self.sensors["distance_m"]
                    self.metrics["frequency_hz"] = (
                        round(220 * 2 ** (2 * (1 - distance)), 1) if distance is not None else None
                    )
            return {
                "verified": self.metrics.get("frequency_hz") is not None,
                "message": "测距已映射为本地音高",
                **self.metrics,
            }
        self.command[:] = 0
        self.command[5] = {"look_left": 0.6, "look_right": -0.6}.get(command.action, 0)
        await self.advance(2)
        self.sensor_frame()
        return {"verified": True, "message": "已更新真实相机与距离采样", **self.metrics}

    async def reset(self):
        await super().reset()
        self.sensor_frame()

    async def close(self):
        await super().close()
        self.renderer.close()
