"""Simple bounded steer-walk used by the race/relay validation scenes.

Unlike stage.navigate it has no A* or stability guard; it steers toward the
goal with a soft repulsion from nearby ducks. Pure bounded velocity commands
on the velstand policy — the same pattern proven in the teletubbies beats.
"""

import asyncio
import math

import numpy as np
from validate_teletubbies import reset_to_walk


async def walk_to(b, i, goal, give_s=25.0, near=0.12):
    reset_to_walk(b, [i])
    d = b.drivers[i]
    start = b.data.time
    while b.data.time - start < give_s:
        pos, yaw = d.pose(b.data)
        to = np.array(goal[:2]) - np.array(pos[:2])
        dist = float(np.linalg.norm(to))
        if dist < near:
            break
        rep = np.zeros(2)
        for k, o in enumerate(b.drivers):
            if k == i:
                continue
            v = np.array(pos[:2]) - o.pose(b.data)[0][:2]
            n = float(np.linalg.norm(v))
            if n < 0.38:
                rep += v / (n + 1e-6) * (0.38 - n)
        bearing = math.atan2(to[1], to[0])
        if float(np.linalg.norm(rep)) > 0.04:
            bearing += 0.55 * math.atan2(rep[1], rep[0])
        error = math.atan2(math.sin(bearing - yaw), math.cos(bearing - yaw))
        speed = min(0.34, max(0.16, dist))
        d.command[:3] = [speed * max(0.25, math.cos(error)), 0,
                         max(-1.0, min(1.0, error * 2.2))]
        await asyncio.sleep(0.02)
    d.command[:3] = 0
    return round(math.dist(d.pose(b.data)[0][:2], goal), 3)
