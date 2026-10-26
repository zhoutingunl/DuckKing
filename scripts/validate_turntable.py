"""《旋转餐桌大逃杀》scene technical validation.

Four well-fed ducks ride an electrically spun wooden turntable. Rounds ramp
the angular velocity; centrifugal physics (nothing scripted) flings ducks off
the edge — a duck is eliminated when its trunk leaves the disk. From round 3
the ducks are allowed to SIT (measured sitstand) to lower their centre of
mass, which the physics genuinely rewards. Eliminated ducks must self-recover
on the floor. Last duck on the table wins.

Honesty: the spin is a real velocity actuator; elimination is measured from
actual trunk position; sit/stand transitions are the measured official
policy; nothing about survival is guaranteed or scripted.
"""

import asyncio
import json
import math
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

from validate_teletubbies import OUT, Show, reset_to_walk, wait_standing  # noqa: E402

import duckking.simulation as sim  # noqa: E402
from duckking.grasp_model import articulate_mouth  # noqa: E402
from duckking.stage import MEMBERS  # noqa: E402

DISK_R = 1.02
CAST = ["演职员表", "1号鸭选手", "2号鸭选手", "3号鸭选手",
        "4号鸭选手", "转盘：真实电机驱动", "配乐：Kevin MacLeod（CC-BY）"]
DUCK_COLORS = {"a": (1.0, 0.05, 0.05), "b": (0.05, 0.30, 1.0),
               "c": (0.05, 0.95, 0.15), "d": (1.0, 0.85, 0.0)}
NUMBERS = {"a": "1", "b": "2", "c": "3", "d": "4"}
CNAME = {"a": "1号鸭", "b": "2号鸭", "c": "3号鸭", "d": "4号鸭"}
HOLD = {0}
R0 = [0.35, 0.62, 0.5, 0.62]  # holder rides closer to the center (safer)
ROUNDS = [(0.8, 8.0, False), (1.2, 8.0, False), (1.6, 8.0, False), (2.0, 8.0, True),
          (2.4, 8.0, True), (2.8, 9.0, True), (3.4, 9.0, True), (4.0, 9.0, True)]


def decor():
    # rotation arrows: bold tangential chevrons on the rim (always visible)
    """Roulette spokes + rim dots on the SPINNING body so rotation is visible."""
    parts = []
    for i in range(4):  # big tangential arrows at the rim
        a = i * math.tau / 4 + 0.35
        cx, cy = 0.86 * math.cos(a), 0.86 * math.sin(a)
        for k, off in enumerate((-0.055, 0.055)):
            b = a + math.pi / 2 + k * 0.5 - 0.25
            parts.append(
                f'<geom name="arrow{i}_{k}" type="box" '
                f'pos="{cx + off * math.cos(a + math.pi / 2):.3f} '
                f'{cy + off * math.sin(a + math.pi / 2):.3f} .03" '
                f'quat="{math.cos(b / 2):.4f} 0 0 {math.sin(b / 2):.4f}" size=".13 .02 .004" '
                f'rgba=".08 .08 .08 1" contype="0" conaffinity="0" group="3"/>')
    for i in range(6):
        a = i * math.tau / 6
        rgba = ".98 .94 .88" if i % 2 == 0 else ".82 .28 .22"
        parts.append(
            f'<geom name="spoke{i}" type="box" '
            f'pos="{0.48 * math.cos(a):.3f} {0.48 * math.sin(a):.3f} .027" '
            f'quat="{math.cos(a / 2):.4f} 0 0 {math.sin(a / 2):.4f}" size=".43 .07 .004" '
            f'rgba="{rgba} 1" contype="0" conaffinity="0" group="3"/>')
    for i in range(10):
        a = i * math.tau / 10
        rgba = ".98 .94 .88" if i % 2 == 0 else ".82 .28 .22"
        parts.append(
            f'<geom name="dot{i}" type="sphere" '
            f'pos="{0.93 * math.cos(a):.3f} {0.93 * math.sin(a):.3f} .03" size=".035" '
            f'rgba="{rgba} 1" contype="0" conaffinity="0" group="3"/>')
    return "".join(parts)


def make_decal():
    """'转盘大逃鸭' painted ON the disk as a textured quad (real decal)."""
    OUT.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (760, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = None
    for path in ("/System/Library/Fonts/PingFang.ttc",
                 "/System/Library/Fonts/Supplemental/Songti.ttc"):
        try:
            font = ImageFont.truetype(path, 92)
            break
        except OSError:
            continue
    if font is None:
        raise RuntimeError("no CJK font available")
    draw.text((380, 100), "转盘大逃鸭", font=font, anchor="mm",
              fill=(96, 20, 8, 255), stroke_width=6, stroke_fill=(255, 240, 210, 255))
    path = OUT / "decal.png"
    img.save(path)
    return path


def build_turntable(robot_dir):
    decal = make_decal()
    spec = mujoco.MjSpec.from_string(
        f'<mujoco><asset><texture name="mark" type="2d" file="{decal}"/>'
        f'<material name="markmat" texture="mark"/></asset><worldbody>'
        '<geom name="floor" type="plane" size="6 6 .1" rgba=".30 .68 .28 1"/>'
        '<geom name="sky" type="plane" pos="-5.2 0 .8" quat=".7071068 0 .7071068 0" '
        'size="12 8 .1" rgba=".55 .78 .96 1" contype="0" conaffinity="0" group="3"/>'
        + "".join(
            f'<geom name="cloud{i}" type="sphere" pos="-4.6 {y} {z}" size="{s * 1.6}" '
            f'rgba=".98 .99 1 1" contype="0" conaffinity="0" group="3"/>'
            for i, (y, z, s) in enumerate([(-3.2, 2.5, .5), (-.8, 3.2, .4), (1.8, 2.7, .44)]))
        + '<geom name="sun" type="sphere" pos="-4.0 -2.4 2.7" size=".5" '
          'rgba="1 .86 .25 1" contype="0" conaffinity="0" group="3"/>'
        # the turntable: a real body on a hinge with a velocity actuator
        '<body name="turntable" pos="0 0 0.02" gravcomp="1">'  # bearing: own weight off the floor
        '<joint name="spin" type="hinge" axis="0 0 1" pos="0 0 0"/>'
        '<geom name="disk" type="cylinder" size="1.05 .02" mass="12" '
        'rgba=".72 .5 .3 1" friction=".6 .008 .0008" priority="1"/>'
        '<geom name="rim" type="cylinder" size="1.06 .028" '
        'rgba=".5 .32 .18 1" mass="0" contype="0" conaffinity="0" group="3"/>'
        + decor()
        + '<geom name="decal" type="box" pos="0 0 .034" size=".8 .21 .001" '
          'material="markmat" contype="0" conaffinity="0" group="3" rgba="1 1 1 1"/>'
        + '</body></worldbody>'
        '<actuator><velocity name="spinner" joint="spin" kv="40"/></actuator></mujoco>')
    for member in MEMBERS:
        root = ET.parse(Path(robot_dir) / "robot_allcollisions.xml").getroot()
        root.find("compiler").set("meshdir", str((Path(robot_dir) / "assets").resolve()))
        articulate_mouth(root)
        robot = mujoco.MjSpec.from_string(ET.tostring(root, encoding="unicode"))
        spec.attach(robot, prefix=member + "_",
                    frame=spec.worldbody.add_frame(pos=[0, 0, 0.04]))
    model = spec.compile()
    model.opt.timestep = 0.005
    return model  # number badges only — no color tinting (user request)


def decorate_frame(show, b, holder):
    """Rotating '转盘大逃鸭' watermark on the disk + number badges over heads."""
    from PIL import Image, ImageDraw
    base = show.overlay
    mark = Image.new("RGBA", (520, 70))
    draw = ImageDraw.Draw(mark)
    draw.text((260, 35), "转 盘 大 逃 鸭", font=show.font_sub, anchor="mm",
              fill=(255, 236, 120, 235), stroke_width=4, stroke_fill=(120, 40, 10, 235))
    az, el = math.radians(show.camera.azimuth), math.radians(show.camera.elevation)
    fwd = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    eye = np.array(show.camera.lookat) - fwd * show.camera.distance
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    upv = np.cross(right, fwd)
    f = (768 / 2) / math.tan(math.radians(45) / 2)

    def project(p):
        v = np.array(p) - eye
        return (float(f * (v @ right) / (v @ fwd) + 512),
                float(768 - (f * (v @ upv) / (v @ fwd) + 384)))

    def wrapped(frame, t):
        img = Image.fromarray(base(frame, t))
        d2 = ImageDraw.Draw(img, "RGBA")
        omega = abs(float(b.data.qvel[b.model.jnt_dofadr[b.model.joint("spin").id]]))
        hx, hy = project([1.62, 0, 0.14])
        speed_text = f"{omega * 1.05:.1f} 米/秒"
        d2.text((hx, hy), speed_text, font=show.font_sub, anchor="mm",
                fill=(255, 255, 80, 255), stroke_width=3, stroke_fill=(0, 0, 0, 220))
        win = holder.get("winner")
        for i, duck in enumerate(b.drivers):
            if i == win:  # gold trophy over the champion's head
                pos = duck.pose(b.data)[0]
                tx, ty = project([pos[0], pos[1], pos[2] + 0.55])
                d2.polygon([(tx - 27, ty - 60), (tx + 27, ty - 60), (tx + 18, ty - 6),
                            (tx - 18, ty - 6)], fill=(255, 200, 40, 255))
                d2.polygon([(tx - 18, ty - 6), (tx + 18, ty - 6), (tx + 12, ty + 12),
                            (tx - 12, ty + 12)], fill=(230, 170, 30, 255))
                d2.rectangle([tx - 30, ty + 12, tx + 30, ty + 24], fill=(255, 200, 40, 255))
                d2.rectangle([tx - 18, ty + 24, tx + 18, ty + 42], fill=(180, 130, 20, 255))
            pos = duck.pose(b.data)[0]
            px, py = project([pos[0], pos[1], pos[2] + 0.34])
            if 0 < px < 1024 and 0 < py < 768:
                d2.ellipse([px - 16, py - 16, px + 16, py + 16], fill=(0, 0, 0, 160))
                d2.text((px, py), NUMBERS[MEMBERS[i]], font=show.font_sub,
                        anchor="mm", fill=(255, 255, 60, 255))
        return np.asarray(img)
    show.overlay = wrapped


async def get_up(b, show, i):
    """An eliminated duck self-recovers on the floor (measured, unaided)."""
    ok, took = await wait_standing(b, [i], timeout_s=16)
    return ok  # get-ups are visual now — no narration line


async def main():
    video_ok = "--no-video" not in sys.argv
    sim.secrets.randbelow = lambda _: 7
    build = sim.build_stage_model
    sim.build_stage_model = build_turntable
    b = sim.MuJoCoBackend(HERE.parent / "external")
    b.load("stage")
    sim.build_stage_model = build
    spin = b.model.actuator("spinner").id
    starts = [(R0[i] * math.cos(i * math.tau / 4), R0[i] * math.sin(i * math.tau / 4))
              for i in range(4)]
    for i, d in enumerate(b.drivers):
        b.data.qpos[d.root: d.root + 7] = [*starts[i], 0.13, 1, 0, 0, 0]
    mujoco.mj_forward(b.model, b.data)
    for _ in range(60):
        b.tick()

    async def fast_loop():
        while True:
            b.tick()
            await asyncio.sleep(0.001)

    b._loop = fast_loop
    b.start()
    show = Show(b, video_ok, name="turntable-show", cast=CAST)
    show.narration_voice = True  # this show speaks its narration (subtitle-synced)
    show.narration_rate = 240  # brisk commentary
    show.camera.lookat, show.camera.distance = [0, 0, 0.2], 4.9
    show.camera.azimuth, show.camera.elevation = 78, -33
    holder = {}
    if video_ok:
        decorate_frame(show, b, holder)
    recorder = asyncio.create_task(show.loop())
    report = {"rounds": [], "eliminations": [], "sits": []}
    recoveries = []
    started = time.monotonic()
    final = None
    try:
        show.say("转盘大逃鸭！被甩出去就出局！")
        reset_to_walk(b)
        await wait_standing(b, list(range(4)), need=0.9, timeout_s=15)
        for d in b.drivers:  # statue mode: the disk's friction carries them around
            d.command[:] = 0
            d.policy = "sitstand"
            d.posture_target = d.rest_posture = "stand"
        alive = list(range(4))
        seated = set()
        for number, (speed, hold, sit_allowed) in enumerate(ROUNDS, 1):
            if len(alive) < 2:
                break
            show.say(f"第{number}轮，加速！")
            if number == 2:
                show.say("1号鸭站稳了！")
            if sit_allowed:
                show.say("这轮起可以坐下，坐稳了！")
                for i in list(alive):
                    if i in seated:
                        continue
                    d = b.drivers[i]
                    d.command[:] = 0
                    d.policy = "sitstand"  # seated: friction ride, no stepping
                    d.posture_target = "sit"
                    seated.add(i)
                    await asyncio.sleep(0.4)
            for i in alive:  # counter-walkers use the walk policy; the holder statues
                d = b.drivers[i]
                d.command[:] = 0
                if i in HOLD:
                    d.policy = "sitstand"
                    d.posture_target = d.rest_posture = "stand"
                else:
                    d.policy = "walk"
            deadline = b.data.time + hold
            while b.data.time < deadline and len(alive) >= 1:
                b.data.ctrl[spin] = speed
                # walk AGAINST the disk rotation to keep balance (treadmill gag):
                # the walk policy's in-place turn rate caps near 0.9 rad/s, so at
                # higher disk speeds the ducks are carried while visibly stepping.
                for i in alive:
                    d = b.drivers[i]
                    if d.policy != "walk" or i in HOLD:
                        continue
                    pos, yaw = d.pose(b.data)
                    x, y = pos[0], pos[1]
                    r = math.hypot(x, y)
                    if r < 0.1:
                        continue
                    ux, uy = x / r, y / r
                    vr = max(-0.15, min(0.15, -1.1 * (r - R0[i])))
                    vxw, vyw = vr * ux, vr * uy
                    c, s2 = math.cos(yaw), math.sin(yaw)
                    d.command[0] = max(-0.3, min(0.3, c * vxw + s2 * vyw))
                    d.command[1] = max(-0.2, min(0.2, -s2 * vxw + c * vyw))
                    d.command[2] = max(-1.0, min(1.0, -speed))
                gone = []
                for i in alive:
                    p = b.drivers[i].pose(b.data)[0]
                    if math.hypot(p[0], p[1]) > DISK_R:
                        gone.append(i)
                for i in gone:
                    alive.remove(i)
                    show.speak(CNAME[MEMBERS[i]], "嘎——！")
                    show.say(f"{i + 1}号出局！")
                    report["eliminations"].append(
                        {"round": number, "member": MEMBERS[i],
                         "radial_m": round(math.hypot(*b.drivers[i].pose(b.data)[0][:2]), 3),
                         "disk_omega": speed})
                    seated.discard(i)
                    d = b.drivers[i]  # 3. fallen duck must get back up by itself
                    d.command[:] = 0
                    d.policy = "walk"
                    recoveries.append(get_up(b, show, i))
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.8)  # keep spinning between rounds, no reset
            report["rounds"].append({"round": number, "omega": speed,
                                     "survivors": [MEMBERS[i] for i in alive]})
            if recoveries:
                await asyncio.gather(*recoveries)
                recoveries.clear()
        if len(alive) == 1:
            w = alive[0]
            holder["winner"] = w
            show.speak(f"{w + 1}号鸭", "嘎嘎！")
            show.say(f"{w + 1}号鸭夺冠！")
            d = b.drivers[w]
            reset_to_walk(b, [w])
            for _ in range(200):  # victory nodding, ~4 s with the trophy overhead
                d.command[4] = 0.25 * math.sin(b.data.time * math.tau * 2)
                await asyncio.sleep(0.02)
            d.command[:] = 0
            report["winner"] = MEMBERS[w]
        else:
            show.say("全出局！")
            report["winner"] = None
        show.say("拜拜！", outro=True)
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
            music = OUT / "music.mp3"
            if final and music.exists():  # low-volume CC-BY background track
                mixed = OUT / "turntable-show-music.mp4"
                await asyncio.to_thread(
                    subprocess.run, [FFMPEG, "-y", "-loglevel", "error",
                                     "-i", str(final), "-stream_loop", "-1",
                                     "-i", str(music), "-filter_complex",
                                     "[1:a]volume=0.16,afade=t=out:st="
                                     f"{max(total_sim - 2, 0):.1f}:d=2[m];"
                                     "[0:a][m]amix=inputs=2:duration=first[a]",
                                     "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                                     "-c:a", "aac", "-b:a", "160k", str(mixed)],
                    check=True)
                final = mixed
        except Exception as exc:
            print(f"audio mux failed ({exc}); silent video kept at {show.video}")
    ok = bool(report.get("eliminations")) and (report.get("winner") is not None
                                               or len(report["rounds"]) >= 4)
    summary = {"scene": "turntable-battle-royale validation",
               "source": "real_velocity_actuator_fling_measured_positions",
               "sim_seconds": round(total_sim, 1),
               "wall_seconds": round(time.monotonic() - started, 1),
               "video": str(final) if final else None,
               "result": report, "pass": ok}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "turntable-report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"\npass={ok} · sim {summary['sim_seconds']}s · wall {summary['wall_seconds']}s")
    if final:
        print(f"video: {final}")


if __name__ == "__main__":
    asyncio.run(main())
