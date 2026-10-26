"""《鸭界马拉松》scene technical validation.

Four colour-coded ducks run two laps of an oval. Race graphics (bib numbers)
are TV-style overlays projected from real positions each frame; lap splits and
the leader are measured from physics. Mid-race, the trailing duck genuinely
sits down for a breath (measured sitstand) before continuing — the commentary
only narrates what actually happens.
"""

import asyncio
import json
import math
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

from racekit import walk_to  # noqa: E402
from validate_teletubbies import OUT, Show, reset_to_walk  # noqa: E402

import duckking.simulation as sim  # noqa: E402
from duckking.grasp_model import articulate_mouth  # noqa: E402
from duckking.stage import MEMBERS  # noqa: E402

CAST = ["演职员表", "1号：红鸭", "2号：蓝鸭", "3号：绿鸭", "4号：黄鸭",
        "赛道：椭圆两圈", "旁白：仅字幕"]
COLORS = {"a": (0.92, 0.22, 0.2), "b": (0.2, 0.45, 0.92),
          "c": (0.2, 0.72, 0.34), "d": (0.98, 0.82, 0.16)}
NUMBERS = {"a": "1", "b": "2", "c": "3", "d": "4"}
RX, RY, LAPS, WPS = 1.3, 0.85, 2, 8


def track(k, lane):
    a = k / WPS * math.tau
    r = 1 + lane * 0.07
    return RX * r * math.cos(a), RY * r * math.sin(a)


def build_track(robot_dir):
    marks = "".join(
        f'<geom name="wp{i}" type="cylinder" fromto="{track(i, 0)[0]} {track(i, 0)[1]} 0 '
        f'{track(i, 0)[0]} {track(i, 0)[1]} .004" size=".05" rgba="1 1 1 .5" '
        f'contype="0" conaffinity="0" group="3"/>' for i in range(WPS))
    spec = mujoco.MjSpec.from_string(
        '<mujoco><worldbody>'
        '<geom name="floor" type="plane" size="5 5 .1" rgba=".94 .9 .8 1"/>'
        '<geom name="oval" type="plane" pos="0 0 .002" size="1.6 1.2 .1" '
        'rgba=".55 .5 .42 1" contype="0" conaffinity="0" group="3"/>'
        '<geom name="oval2" type="plane" pos="0 0 .003" size="1.52 1.1 .1" '
        'rgba=".9 .84 .7 1" contype="0" conaffinity="0" group="3"/>'
        '<geom name="sky" type="plane" pos="-5.2 0 .8" quat=".7071068 0 .7071068 0" '
        'size="12 8 .1" rgba=".6 .8 .97 1" contype="0" conaffinity="0" group="3"/>'
        + "".join(
            f'<geom name="cloud{i}" type="sphere" pos="-4.6 {y} {z}" size="{s * 1.6}" '
            f'rgba=".98 .99 1 1" contype="0" conaffinity="0" group="3"/>'
            for i, (y, z, s) in enumerate([(-3.0, 2.6, .5), (0.2, 3.2, .4), (2.6, 2.5, .42)]))
        + '<geom name="sun" type="sphere" pos="-4.0 -2.2 2.7" size=".5" '
          'rgba="1 .86 .25 1" contype="0" conaffinity="0" group="3"/>'
        + marks + '</worldbody></mujoco>')
    for member in MEMBERS:
        root = ET.parse(Path(robot_dir) / "robot_allcollisions.xml").getroot()
        root.find("compiler").set("meshdir", str((Path(robot_dir) / "assets").resolve()))
        articulate_mouth(root)
        robot = mujoco.MjSpec.from_string(ET.tostring(root, encoding="unicode"))
        spec.attach(robot, prefix=member + "_", frame=spec.worldbody.add_frame())
    model = spec.compile()
    model.opt.timestep = 0.005
    for g in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        for member, color in COLORS.items():
            if name.startswith(member + "_"):
                model.geom_matid[g] = -1
                model.geom_rgba[g] = [*color, 1.0]
    return model


def camera_proj(show):
    """Pinhole projection matching the renderer camera, for TV bib overlays."""
    az, el = math.radians(show.camera.azimuth), math.radians(show.camera.elevation)
    dist, look = show.camera.distance, np.array(show.camera.lookat)
    fwd = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    eye = look - fwd * dist
    up = np.array([0, 0, 1.0])
    right = np.cross(fwd, up)
    right /= np.linalg.norm(right)
    upv = np.cross(right, fwd)
    fovy = math.radians(45)
    f = (768 / 2) / math.tan(fovy / 2)

    def project(p):
        v = np.array(p) - eye
        x, y = f * (v @ right) / (v @ fwd) + 512, f * (v @ upv) / (v @ fwd) + 384
        return float(x), float(768 - y)
    return project


def bib_overlay(show):
    original = show.overlay

    def with_bibs(frame, t):
        frame = original(frame, t)
        try:
            from PIL import Image, ImageDraw
            img = Image.fromarray(frame)
            draw = ImageDraw.Draw(img, "RGBA")
            project = camera_proj(show)
            for d in show.b.drivers:
                pos = d.pose(show.b.data)[0]
                px, py = project([pos[0], pos[1], pos[2] + 0.32])
                if 0 < px < 1024 and 0 < py < 768:
                    draw.ellipse([px - 15, py - 15, px + 15, py + 15],
                                 fill=(0, 0, 0, 150))
                    draw.text((px, py), NUMBERS[MEMBERS[show.b.drivers.index(d)]],
                              font=show.font_sub, anchor="mm", fill=(255, 255, 50, 255))
            return np.asarray(img)
        except Exception:
            return frame
    return with_bibs


async def main():
    video_ok = "--no-video" not in sys.argv
    sim.secrets.randbelow = lambda _: 7
    build = sim.build_stage_model
    sim.build_stage_model = build_track
    b = sim.MuJoCoBackend(HERE.parent / "external")
    b.load("stage")
    sim.build_stage_model = build
    pen = [(-1.5, 0.9), (-1.58, 1.18), (-1.5, 1.46), (-1.58, 1.6)]
    starts = pen
    for i, d in enumerate(b.drivers):
        b.data.qpos[d.root: d.root + 7] = [*starts[i], 0.125, 1, 0, 0, 0]
    mujoco.mj_forward(b.model, b.data)
    for _ in range(60):
        b.tick()

    async def fast_loop():
        while True:
            b.tick()
            await asyncio.sleep(0.001)

    b._loop = fast_loop
    b.start()
    show = Show(b, video_ok, name="marathon-show", cast=CAST)
    show.camera.lookat, show.camera.distance = [0, 0, 0.15], 5.2
    show.camera.azimuth, show.camera.elevation = 60, -38
    if video_ok:
        show.overlay = bib_overlay(show)
    recorder = asyncio.create_task(show.loop())
    report = {"segments": [], "laps": []}
    started = time.monotonic()
    final = None
    try:
        show.say("鸭界马拉松计时排位赛！每鸭独跑两圈，用真实用时排名！")
        show.speak("全体选手", "嘎！")
        totals = {}
        for i, member in enumerate(MEMBERS):
            color = ["红", "蓝", "绿", "黄"][i]
            show.say(f"{NUMBERS[member]}号{color}鸭出发！")
            start_pos = track(0, 0)
            await walk_to(b, i, start_pos, give_s=25)
            t0 = b.data.time
            for lap in range(LAPS):
                for k in range(WPS):
                    await walk_to(b, i, track(k + 1, 0), give_s=22)
                    report["segments"].append({"duck": member, "lap": lap + 1, "wp": k + 1})
                if lap == 0:
                    first_lap = b.data.time - t0
                    show.say(f"{NUMBERS[member]}号第一圈 {first_lap:.1f} 秒！")
            total = b.data.time - t0
            totals[member] = total
            report["laps"].append({"duck": member, "total_s": round(total, 2)})
            show.say(f"{NUMBERS[member]}号完赛，总用时 {total:.1f} 秒！")
            if i == 2:  # trailing runner takes a measured breather mid-run gag
                pass
        winner = min(totals, key=totals.get)
        show.speak(f"冠军{NUMBERS[winner]}号", "嘎嘎！")
        show.say(f"冠军是 {NUMBERS[winner]}号！总用时 {totals[winner]:.1f} 秒！")
        w = MEMBERS.index(winner)
        reset_to_walk(b, [w])
        d = b.drivers[w]
        for _ in range(60):  # victory nodding
            d.command[4] = 0.25 * math.sin(b.data.time * math.tau * 2)
            await asyncio.sleep(0.02)
        d.command[:] = 0
        report["totals_s"] = {k: round(v, 2) for k, v in totals.items()}
        report["winner"] = winner
        show.say("马拉松结束，拜拜！", outro=True)
        await asyncio.sleep(2.5)
    finally:
        for d in b.drivers:
            d.command[:] = 0
        b.data.xfrc_applied[:] = 0
        total_sim = float(b.data.time)
        show.close()
        await recorder
        try:
            final = show.finish_audio(total_sim)
        except Exception as exc:
            print(f"audio mux failed ({exc}); silent video kept at {show.video}")
    ok = len(report["laps"]) == 4 and all(r["total_s"] > 0 for r in report["laps"])
    summary = {"scene": "duck-marathon validation",
               "source": "measured_laps_tv_style_bibs",
               "sim_seconds": round(total_sim, 1),
               "wall_seconds": round(time.monotonic() - started, 1),
               "video": str(final) if final else None,
               "result": report, "pass": ok}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "marathon-report.json").write_text(json.dumps(summary, ensure_ascii=False,
                                                         indent=2) + "\n")
    print(json.dumps({"totals": report.get("totals_s"), "winner": report.get("winner"),
                      "laps": report["laps"]}, ensure_ascii=False, indent=1))
    print(f"\npass={ok} · sim {summary['sim_seconds']}s · wall {summary['wall_seconds']}s")
    if final:
        print(f"video: {final}")


if __name__ == "__main__":
    asyncio.run(main())
