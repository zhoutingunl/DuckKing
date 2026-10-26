"""Measured sit/stand transitions using the official 61D sitstand policy."""

import asyncio
import math
import time


def request_posture(driver, target):
    driver.command[:] = 0
    driver.policy = "sitstand"
    driver.posture_target = target


def measure_posture(backend, driver):
    data = backend.data
    surface = backend.model.geom(
        "table_top" if backend.scene == "seated"
        else "disk" if backend.scene == "turntable" else "floor").id
    surface_z = 0.4 if backend.scene == "seated" else 0.04 if backend.scene == "turntable" else 0
    height = float(data.qpos[driver.root + 2]) - surface_z
    upright = float(data.xmat[driver.body, 8])
    knees = [abs(float(data.qpos[driver.q[j]])) for j in (3, 12)]
    supported = any(
        (int(c.geom1) == surface and int(c.geom2) in driver.contact_geoms)
        or (int(c.geom2) == surface and int(c.geom1) in driver.contact_geoms)
        for c in data.contact
    )
    observed = "transition"
    if supported and upright > 0.94:
        if 0.045 < height < 0.078 and min(knees) > 1.0:
            observed = "sit"
        elif 0.10 < height < 0.145 and max(knees) < 0.55:
            observed = "stand"
    return {
        "target": driver.posture_target,
        "observed": observed,
        "supported": supported,
        "height_m": height,
        "upright": upright,
        "knee_deg": [math.degrees(v) for v in knees],
    }


async def change_posture(backend, drivers, target, duration=3.0):
    starts = [d.pose(backend.data)[0][:2].copy() for d in drivers]
    for driver in drivers:
        request_posture(driver, target)
    deadline = time.monotonic() + duration
    stable_since = None
    while time.monotonic() < deadline:
        backend.ensure_running()
        measurements = [measure_posture(backend, d) for d in drivers]
        if any(
            math.dist(d.pose(backend.data)[0][:2], p) > 0.10
            for d, p in zip(drivers, starts, strict=True)
        ):
            raise ValueError("坐站动作偏离原位，已停止")
        if all(m["observed"] == target for m in measurements):
            if stable_since is None:
                stable_since = float(backend.data.time)
            if backend.data.time - stable_since >= 0.3:
                for driver in drivers:
                    driver.rest_posture = target
                return {
                    "verified": True,
                    "posture": target,
                    "ducks": measurements,
                    "source": "official_sitstand_measured_contacts",
                }
        else:
            stable_since = None
        await asyncio.sleep(0.02)
    raise ValueError("未在时限内确认坐稳或站稳，已停止；请重置后重试")
