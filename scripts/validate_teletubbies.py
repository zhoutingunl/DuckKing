"""《鸭鸭宝宝》(Teletubbies-ducks) scene technical validation, show edition.

Upgrades over the bare validation, all honest and physics-clean:
  - Saturated flat colors per duck (丁丁紫/迪西绿/拉拉黄/小波红): materials are
    cleared so the tint cannot be washed out by textures.
  - Teletubbies set: sky backdrop + clouds + sun as STATIC world geoms with
    contype=conaffinity=0 (visual only, zero dynamics), vivid green floor.
  - Event-driven Tingting narration (macOS system voice, repo convention):
    each line is emitted only when the measured event actually happens, e.g.
    "它自己站起来啦" plays only after real recovery is measured.
  - Continuous frame capture for the whole show (one frame per 0.05 s of
    SIMULATION time at 20 fps, so video pace == physics pace).

Beats and measurement logic are unchanged from the validated script:
B1 gather, B2 solo walk-up + nod/tilt, B3 bounded-push fall + unaided velstand
recovery, B4 hug until real contact, B5 in-place 360 spin, B6 "again again".
"""

import asyncio
import json
import math
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import mujoco
import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFont
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckking.simulation as sim  # noqa: E402
from duckking.grasp_model import articulate_mouth  # noqa: E402
from duckking.stage import MEMBERS, SLOTS  # noqa: E402

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
OUT = ROOT / ".duckking" / "teletubbies"
CAST = ["演职员表", "丁丁：鸭鸭A", "迪西：鸭鸭B", "拉拉：鸭鸭C", "小波：鸭鸭D",
        "客串：三只小羊", "旁白：仅字幕", "太阳宝宝：本地合成笑声"]
CREDITS_END = 9.0  # opening credits show for the first 9 s


def props_xml():
    """Trees, sheep, grass tufts, river, sun rays and a parked scooter.
    All static world geoms with collision disabled (visual only)."""
    out = []
    # river across the back, with ripples
    out.append('<geom name="river" type="plane" pos="-2.5 0 .012" size=".55 3.8 .1" '
               'rgba=".35 .62 .92 1" contype="0" conaffinity="0" group="3"/>')
    for i, (y, x) in enumerate([(-1.2, -2.5), (0.4, -2.42), (1.6, -2.56)]):
        out.append(f'<geom name="ripple{i}" type="ellipsoid" pos="{x} {y} .02" '
                   f'size=".09 .028 .008" rgba=".92 .96 1 .8" contype="0" conaffinity="0" '
                   f'group="3"/>')
    # trees
    for i, (x, y, h) in enumerate([(-3.4, -2.6, .55), (-3.5, -.6, .72), (-3.3, 1.1, .62),
                                   (-3.6, 2.6, .5)]):
        out.append(f'<geom name="trunk{i}" type="cylinder" '
                   f'fromto="{x} {y} 0 {x} {y} {h}" size=".045" rgba=".42 .28 .16 1" '
                   f'contype="0" conaffinity="0" group="3"/>')
        for j, (r, dz, c) in enumerate([(.23, .1, ".22 .55 .24"), (.16, .3, ".26 .6 .2"),
                                        (.12, .44, ".3 .66 .22")]):
            out.append(f'<geom name="leaf{i}_{j}" type="sphere" pos="{x} {y} {h + dz}" '
                       f'size="{r}" rgba="{c} 1" contype="0" conaffinity="0" group="3"/>')
    # three sheep
    for i, (x, y, face) in enumerate([(-2.05, -1.7, 1), (-2.15, 1.95, -1), (-1.9, -2.35, 1)]):
        out.append(f'<geom name="sheep{i}_body" type="ellipsoid" pos="{x} {y} .16" '
                   f'size=".13 .09 .085" rgba=".95 .94 .9 1" contype="0" conaffinity="0" '
                   f'group="3"/>')
        out.append(f'<geom name="sheep{i}_head" type="sphere" '
                   f'pos="{x} {y + .13 * face} .2" size=".05" rgba=".25 .23 .22 1" '
                   f'contype="0" conaffinity="0" group="3"/>')
        for ly in (-.05, .05):
            out.append(f'<geom name="sheep{i}_leg{ly}" type="cylinder" '
                       f'fromto="{x} {y + ly} 0 {x} {y + ly} .09" size=".012" '
                       f'rgba=".3 .28 .26 1" contype="0" conaffinity="0" group="3"/>')
    # a parked kick scooter, leaning by the trees
    out.append('<geom name="scooter_deck" type="capsule" '
               'fromto="-2.0 2.25 .05 -2.0 2.62 .05" size=".028" rgba=".85 .2 .2 1" '
               'contype="0" conaffinity="0" group="3"/>')
    for wy in (2.28, 2.6):
        out.append(f'<geom name="scooter_wheel{int(wy * 100)}" type="cylinder" '
                   f'fromto="-2.05 {wy} .035 -1.95 {wy} .035" size=".035" '
                   f'rgba=".15 .15 .15 1" contype="0" conaffinity="0" group="3"/>')
    out.append('<geom name="scooter_column" type="cylinder" '
               'fromto="-2.0 2.62 .07 -2.0 2.6 .6" size=".014" rgba=".75 .77 .8 1" '
               'contype="0" conaffinity="0" group="3"/>')
    out.append('<geom name="scooter_bar" type="cylinder" '
               'fromto="-2.0 2.5 .6 -2.0 2.68 .6" size=".013" rgba=".2 .2 .22 1" '
               'contype="0" conaffinity="0" group="3"/>')
    # sun rays
    for k in range(8):
        a = k * math.tau / 8
        dy, dz = math.cos(a), math.sin(a)
        out.append(f'<geom name="ray{k}" type="cylinder" '
                   f'fromto="-3.2 {-2.2 + dy * .55} {2.6 + dz * .55} '
                   f'-3.2 {-2.2 + dy * .74} {2.6 + dz * .74}" size=".012" '
                   f'rgba="1 .85 .3 1" contype="0" conaffinity="0" group="3"/>')
    # grass tufts along the sides and the back
    tufts = [(-1.5, 1.6), (-1.8, -1.9), (-1.4, -1.5), (-2.2, .9), (-2.9, -1.0),
             (-2.2, -2.9), (-3.1, .3), (-1.6, 2.3), (-1.3, -2.6), (-3.0, 2.0),
             (1.4, 1.7), (1.5, -1.6), (2.2, 1.2), (2.3, -1.3), (1.2, -2.4), (1.1, 2.5)]
    for i, (x, y) in enumerate(tufts):
        out.append(f'<geom name="tuft{i}" type="ellipsoid" pos="{x} {y} .05" '
                   f'size=".05 .05 .08" rgba=".3 .72 .25 1" contype="0" conaffinity="0" '
                   f'group="3"/>')
    return "".join(out)
COLORS = {  # 丁丁 / 迪西 / 拉拉 / 小波  (saturated, cartoon-flat)
    "a": (0.48, 0.22, 0.72),
    "b": (0.14, 0.62, 0.30),
    "c": (0.98, 0.80, 0.10),
    "d": (0.90, 0.18, 0.22),
}
NAMES = {"a": "丁丁", "b": "迪西", "c": "拉拉", "d": "小波"}
FRONT_STEP = 0.35
SUN_GIGGLE = "咿嘻嘻嘻嘻"
NARRATOR_CACHE = {}


def decorate(robot_dir):
    """Cartoon set + flat duck colors, built like the official stage model.
    Decorations are static world geoms with collision disabled — they cannot
    touch the physics in any way."""
    import xml.etree.ElementTree as ET
    robot_dir = Path(robot_dir)
    spec = mujoco.MjSpec.from_string(
        '<mujoco><worldbody>'
        '<geom name="floor" type="plane" size="4 4 .1" rgba=".30 .68 .28 1" '
        'friction="1 .01 .001"/>'
        '<geom name="sky" type="plane" pos="-4.2 0 .8" quat=".7071068 0 .7071068 0" '
        'size="12 8 .1" rgba=".55 .78 .96 1" contype="0" conaffinity="0" group="3"/>'
        + "".join(
            f'<geom name="cloud{i}" type="sphere" pos="-3.6 {y} {z}" size="{s * 1.6}" '
            f'rgba=".98 .99 1 1" contype="0" conaffinity="0" group="3"/>'
            for i, (y, z, s) in enumerate(
                [(-3.2, 2.4, .5), (-1.0, 3.1, .38), (1.6, 2.6, .44), (3.4, 2.2, .34),
                 (0.2, 1.9, .28)]))
        + '<geom name="sun" type="sphere" pos="-3.2 -2.2 2.6" size=".42" '
          'rgba="1 .86 .25 1" contype="0" conaffinity="0" group="3"/>'
        + props_xml()
        + '</worldbody></mujoco>')
    for member in MEMBERS:
        root = ET.parse(robot_dir / "robot_allcollisions.xml").getroot()
        root.find("compiler").set("meshdir", str((robot_dir / "assets").resolve()))
        articulate_mouth(root)
        robot = mujoco.MjSpec.from_string(ET.tostring(root, encoding="unicode"))
        spec.attach(robot, prefix=member + "_", frame=spec.worldbody.add_frame())
    model = spec.compile()
    model.opt.timestep = 0.005
    # flat cartoon colors: clear materials so nothing washes the tint out
    for g in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        for member, color in COLORS.items():
            if name.startswith(member + "_"):
                model.geom_matid[g] = -1
                model.geom_rgba[g] = [*color, 1.0]
    return model


def narrate(text, rate=185):
    """macOS Tingting synthesis, disclosed repo convention; cached per text."""
    if text not in NARRATOR_CACHE:
        wav = OUT / f"line{len(NARRATOR_CACHE)}.wav"
        wav.parent.mkdir(parents=True, exist_ok=True)
        aiff = wav.with_suffix(".aiff")
        subprocess.run(["say", "-v", "Tingting", "-r", str(rate), "-o", str(aiff), text],
                       check=True)
        subprocess.run([FFMPEG, "-y", "-loglevel", "error",
                        "-i", str(aiff), "-ar", "22050", "-ac", "1", str(wav)], check=True)
        aiff.unlink()
        with wave.open(str(wav)) as w:
            NARRATOR_CACHE[text] = (wav, w.getnframes() / w.getframerate())
    return NARRATOR_CACHE[text]


class Show:
    """Continuous sim-time-paced recording + event-driven narration track."""

    def __init__(self, b, enabled=True, name="teletubbies-show", cast=None):
        self.b, self.enabled = b, enabled
        self.cast = cast if cast is not None else CAST
        self.done = False
        self.frames = 0
        self.cues = []  # (sim_time, text)
        self.cue_dur = {}  # text -> synthesized seconds
        self.outro_at = None
        self.cue_until = 0.0  # serialize: each line waits for the previous one
        self.last = -1.0
        self.renderer = None
        self.font_sub = self.font_cast = None
        if enabled:
            self.b.model.vis.global_.offwidth = 1024
            self.b.model.vis.global_.offheight = 768
            self.renderer = mujoco.Renderer(self.b.model, height=768, width=1024)
            self.camera = mujoco.MjvCamera()
            self.camera.lookat, self.camera.distance = [0.0, 0.0, 0.18], 4.3
            self.camera.azimuth, self.camera.elevation = 90, -24
            if HAVE_PIL:
                for path in ("/System/Library/Fonts/PingFang.ttc",
                             "/System/Library/Fonts/Supplemental/Songti.ttc"):
                    try:
                        self.font_sub = ImageFont.truetype(path, 30)
                        self.font_cast = ImageFont.truetype(path, 24)
                        break
                    except OSError:
                        continue
            OUT.mkdir(parents=True, exist_ok=True)
            self.video = OUT / f"{name}.mp4"
            self.encoder = subprocess.Popen(
                [FFMPEG, "-y", "-loglevel", "error",
                 "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1024x768", "-r", "20",
                 "-i", "-", "-an", "-c:v", "libx264", "-crf", "23", "-preset",
                 "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                 str(self.video)], stdin=subprocess.PIPE)

    def overlay(self, frame, t):
        """Burn subtitles (bottom) and the cast panel (right, opening + outro)
        straight into the frame — this static ffmpeg has no drawtext."""
        img = Image.fromarray(frame)
        draw = ImageDraw.Draw(img, "RGBA")
        width, height = img.size
        if t <= CREDITS_END or (self.outro_at is not None and t >= self.outro_at):
            panel_w, line_h = 268, 34
            x1, y1 = width - panel_w - 14, 64
            draw.rounded_rectangle([x1, y1, width - 14, y1 + line_h * len(self.cast) + 18],
                                   radius=12, fill=(0, 0, 0, 130))
            for k, line in enumerate(self.cast):
                color = (255, 224, 90, 255) if k == 0 else (255, 255, 255, 255)
                draw.text((x1 + 18, y1 + 14 + k * line_h), line, font=self.font_cast,
                          fill=color)
        y = height - 44
        for cue in self.cues:
            if cue["t"] <= t < cue["t"] + cue["dur"]:
                draw.text((width // 2, y), cue["text"], font=self.font_sub, anchor="mm",
                          fill=(255, 255, 255, 255), stroke_width=3,
                          stroke_fill=(0, 0, 0, 220))
                y -= 42
        return np.asarray(img)

    def say(self, text, at=None, outro=False):
        """Narrator line: subtitle only by default; voiced when
        self.narration_voice is set (subtitle and audio share one cue)."""
        if not self.enabled:
            return
        t = self.b.data.time if at is None else at
        if getattr(self, "narration_voice", False):
            wav, seconds = narrate(text, getattr(self, "narration_rate", 185))
            start = max(t, self.cue_until + 0.15)
            self.cues.append({"t": start, "text": text, "dur": seconds + 0.1, "wav": wav})
            self.cue_until = start + seconds
        else:
            self.cues.append({"t": t, "text": text,
                              "dur": max(1.6, len(text) / 3.0) + 0.8, "wav": None})
        if outro:
            self.outro_at = t

    def speak(self, speaker, words, rate=185):
        """A character actually speaks: voiced + 'speaker：words' subtitle."""
        if not self.enabled:
            return
        t = self.b.data.time
        wav, seconds = narrate(words, rate)
        start = max(t, self.cue_until + 0.15)
        self.cues.append({"t": start, "text": f"{speaker}：{words}",
                          "dur": seconds + 0.6, "wav": wav})
        self.cue_until = start + seconds
        self.cue_dur[words] = seconds

    async def loop(self):
        while not self.done:
            if self.b.data.time - self.last >= 0.05:
                self.last = self.b.data.time
                self.renderer.update_scene(self.b.data, camera=self.camera)
                frame = self.renderer.render()
                if self.font_sub is not None:
                    frame = self.overlay(frame, self.b.data.time)
                self.encoder.stdin.write(np.ascontiguousarray(frame).tobytes())
                self.frames += 1
            await asyncio.sleep(0.002)

    def finish_audio(self, total_sim_s):
        if not self.enabled or not self.cues:
            return None
        rate, seconds = 22050, math.ceil(total_sim_s) + 2
        track = np.zeros(seconds * rate, dtype=np.float32)
        spoken = [c for c in self.cues if c["wav"] is not None]
        for cue in spoken:
            with wave.open(str(cue["wav"])) as w:
                data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
            start = int(cue["t"] * rate)
            end = min(start + len(data), len(track))
            track[start:end] = np.maximum(track[start:end],
                                          data[: end - start].astype(np.float32) / 32768 * .95)
        mixed = OUT / "narration.wav"
        with wave.open(str(mixed), "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes((np.clip(track, -1, 1) * 32767).astype(np.int16).tobytes())
        final = OUT / f"{self.video.stem}-final.mp4"
        # NB: this static ffmpeg build has no drawtext filter; the color->name
        # mapping is narrated instead ("紫色的丁丁…说，诶哦！").
        subprocess.run([FFMPEG, "-y", "-loglevel", "error",
                        "-i", str(self.video), "-i", str(mixed),
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest",
                        str(final)], check=True)
        return final

    def close(self):
        self.done = True
        if self.encoder:
            self.encoder.stdin.close()
            self.encoder.wait()
        if self.renderer:
            self.renderer.close()


def upright(b, i):
    return float(b.data.xmat[b.drivers[i].body, 8])


def reset_to_walk(b, indices=None):
    """navigate() parks arrived ducks on the sitstand policy, which ignores
    velocity commands. Manual beats need the velstand (walk) policy back."""
    for i in range(4) if indices is None else indices:
        d = b.drivers[i]
        d.command[:] = 0
        if d.policy == "sitstand":
            d.policy = "walk"
            d.posture_target = d.rest_posture = "stand"


async def wait_standing(b, indices, need=0.94, sustain=0.5, timeout_s=15):
    stable, start = None, float(b.data.time)
    while b.data.time - start < timeout_s:
        b.ensure_running()
        if all(upright(b, i) > need for i in indices):
            stable = b.data.time if stable is None else stable
            if b.data.time - stable >= sustain:
                return True, b.data.time - start
        else:
            stable = None
        await asyncio.sleep(0.005)
    return False, b.data.time - start


async def beat_solo(b, show, report):
    """B2: each member walks to the front, nods twice + tilts, walks back."""
    for i, member in enumerate(MEMBERS):
        color = ['紫色', '绿色', '黄色', '红色'][i]
        show.say(f"{color}的{NAMES[member]}走上前来")
        await asyncio.sleep(1.2)
        slot = SLOTS[i]
        await b.stage.navigate([i], {i: (slot[0] + FRONT_STEP, slot[1])}, max_seconds=12)
        show.speak(f"{color}的{NAMES[member]}", "诶哦！")
        d = b.drivers[i]
        start, forward_max = b.data.time, 0.0
        while b.data.time - start < 1.8:
            t = b.data.time - start
            d.command[:3] = 0
            d.command[4] = 0.22 * math.sin(t * math.tau * 2)
            d.command[6] = 0.20 * math.sin(t * math.pi)
            forward_max = max(forward_max, d.pose(b.data)[0][0] - slot[0])
            await asyncio.sleep(0.005)
        await b.stage.navigate([i], {i: slot}, max_seconds=12)
        back = math.dist(b.drivers[i].pose(b.data)[0][:2], slot)
        ok = forward_max > 0.2 and back < 0.2 and upright(b, i) > 0.9
        report.append({"beat": "solo", "member": member, "forward_m": round(forward_max, 3),
                       "returned_gap_m": round(back, 3), "standing": upright(b, i) > 0.9,
                       "pass": bool(ok)})


async def beat_falls(b, show, report, tag):
    """B3/B6: bounded push knocks each duck; velstand must recover unaided.
    Narration is event-driven: the 'got up' line only plays on measured recovery."""
    for i, member in enumerate(MEMBERS):
        reset_to_walk(b, [i])
        ok_stand, _ = await wait_standing(b, [i], timeout_s=12)
        if not ok_stand:
            show.say(f"{NAMES[member]}还在躺平，先不起来了")
            report.append({"beat": tag, "member": member, "pass": False,
                           "reason": "未能先站稳"})
            continue
        d = b.drivers[i]
        fell, force_used = False, 0.0
        for force, duration, direction in ((4.5, 0.25, 1), (6.0, 0.25, -1), (8.0, 0.3, 1)):
            d.command[:] = 0
            push_until = b.data.time + duration
            min_up = 1.0
            while b.data.time < push_until:
                b.data.xfrc_applied[d.body, :3] = [force * direction, 0, 0]
                min_up = min(min_up, upright(b, i))
                await asyncio.sleep(0.002)
            b.data.xfrc_applied[:] = 0
            d.command[:] = 0
            watch_until = b.data.time + 1.5
            while b.data.time < watch_until and min_up >= 0.45:
                min_up = min(min_up, upright(b, i))
                await asyncio.sleep(0.005)
            if min_up < 0.45:
                fell, force_used = True, force
                break
        if fell:
            show.say(f"哎呀，{NAMES[member]}摔啦！")
        recovered, took = (False, None)
        if fell:
            d.command[:] = 0
            recovered, took = await wait_standing(b, [i], timeout_s=14)
            if recovered:
                show.say(f"看！{NAMES[member]}自己站起来啦！")
        report.append({"beat": tag, "member": member, "fell": fell,
                       "force_n": force_used, "recovered_unaided": recovered,
                       "recovery_s": round(took, 2) if took else None,
                       "pass": bool(fell and recovered)})


async def beat_hug(b, show, report):
    """B4: the two middle ducks meet until REAL body contact, then return."""
    i, j = 1, 2
    show.say(f"{NAMES[MEMBERS[i]]}和{NAMES[MEMBERS[j]]}，抱一个！")
    mid = ((SLOTS[i][0] + SLOTS[j][0]) / 2, (SLOTS[i][1] + SLOTS[j][1]) / 2)
    reset_to_walk(b)
    await wait_standing(b, [0, 1, 2, 3], need=0.9, timeout_s=15)
    for attempt in range(2):  # a wobbly post-fall duck can trip the stage guard
        try:
            await b.stage.navigate(list(range(4)), dict(enumerate(SLOTS)), max_seconds=30)
            break
        except ValueError:
            if attempt:
                raise
            await wait_standing(b, [0, 1, 2, 3], need=0.85, timeout_s=15)
    await b.stage.navigate([i], {i: (mid[0], mid[1] - 0.15)}, max_seconds=25)
    await b.stage.navigate([j], {j: (mid[0], mid[1] + 0.15)}, max_seconds=25)
    reset_to_walk(b, [i, j])
    owners = b.geom_owner
    pair_found, deadline = False, b.data.time + 8
    while b.data.time < deadline and not pair_found:
        for c in b.data.contact:
            if {owners[int(c.geom1)], owners[int(c.geom2)]} == {i, j}:
                pair_found = True
                break
        if not pair_found:
            for k, sign in ((i, -1), (j, 1)):
                d = b.drivers[k]
                pos, yaw = d.pose(b.data)
                bearing = math.atan2(mid[1] + sign * 0.05 - pos[1], mid[0] - pos[0])
                error = math.atan2(math.sin(bearing - yaw), math.cos(bearing - yaw))
                d.command[:3] = [0.10 * max(0.2, math.cos(error)), 0,
                                 max(-1, min(1, error * 2))]
        await asyncio.sleep(0.02)
    for k in (i, j):
        b.drivers[k].command[:] = 0
    if pair_found:
        show.say("抱到啦！")
    await wait_standing(b, [i, j], need=0.75, timeout_s=10)
    await b.stage.navigate([i, j], {i: SLOTS[i], j: SLOTS[j]}, max_seconds=15)
    ok = pair_found and all(upright(b, k) > 0.85 for k in (i, j))
    report.append({"beat": "hug", "pair": [MEMBERS[i], MEMBERS[j]],
                   "real_contact": pair_found,
                   "both_upright": all(upright(b, k) > 0.85 for k in (i, j)),
                   "pass": bool(ok)})


async def beat_spin(b, show, report):
    """B5: each duck turns a full 360° in place with a bounded yaw command."""
    show.say("转圈圈咯！")
    for i, member in enumerate(MEMBERS):
        d = b.drivers[i]
        reset_to_walk(b, [i])
        last = d.pose(b.data)[1]
        total, start = 0.0, b.data.time
        while b.data.time - start < 9.5 and abs(total) < math.tau * 0.95:
            d.command[:3] = [0, 0, 0.85]
            yaw = d.pose(b.data)[1]
            total += math.atan2(math.sin(yaw - last), math.cos(yaw - last))
            last = yaw
            await asyncio.sleep(0.005)
        d.command[:] = 0
        ok_stand, _ = await wait_standing(b, [i], timeout_s=10)
        ok = abs(total) >= math.tau * 0.9 and ok_stand
        report.append({"beat": "spin", "member": member,
                       "yaw_turned_rad": round(total, 2),
                       "turns": round(abs(total) / math.tau, 2),
                       "standing_after": ok_stand, "pass": bool(ok)})


async def main():
    video_ok = "--no-video" not in sys.argv
    sim.secrets.randbelow = lambda _: 7
    original_build = sim.build_stage_model
    sim.build_stage_model = decorate
    b = sim.MuJoCoBackend(ROOT / "external")
    b.load("stage")
    sim.build_stage_model = original_build

    async def fast_loop():
        while True:
            b.tick()
            await asyncio.sleep(0.001)

    b._loop = fast_loop
    b.start()
    show = Show(b, video_ok)
    recorder = asyncio.create_task(show.loop())
    report = []
    started = time.monotonic()
    final_video = None
    try:
        show.say("太阳宝宝升起来啦！")
        show.speak("太阳宝宝", SUN_GIGGLE, rate=210)
        show.say("鸭鸭宝宝们，开播啦！")
        for name, fn in (("gather", None), ("solo", beat_solo),
                         ("fall_recovery", None), ("hug", beat_hug), ("spin", beat_spin),
                         ("again_again", None)):
            try:
                if name == "gather":
                    await b.stage.gather()  # B1
                    show.say("四只鸭鸭宝宝，集合完毕！")
                    gaps = [round(math.dist(b.drivers[i].pose(b.data)[0][:2], SLOTS[i]), 3)
                            for i in range(4)]
                    standing = all(upright(b, i) > 0.9 for i in range(4))
                    report.append({"beat": "gather", "slot_gaps_m": gaps,
                                   "all_standing": standing,
                                   "pass": bool(max(gaps) < 0.2 and standing)})
                elif name in ("fall_recovery", "again_again"):
                    if name == "again_again":
                        show.say("安哥安哥！再来一次！")
                    await beat_falls(b, show, report, name)
                else:
                    await fn(b, show, report)
            except Exception as exc:  # one failed beat must not kill the show
                report.append({"beat": name, "pass": False, "error": str(exc)[:160]})
        show.say("太阳下山啦。", outro=True)
        show.speak("鸭鸭宝宝们", "拜拜，拜拜！")
        await asyncio.sleep(2.5)
    finally:
        for d in b.drivers:
            d.command[:] = 0
        b.data.xfrc_applied[:] = 0
        total_sim = float(b.data.time)
        show.close()
        await recorder
        try:
            final_video = show.finish_audio(total_sim)
        except Exception as exc:
            print(f"audio mux failed ({exc}); silent video kept at {show.video}")
    passed = sum(1 for r in report if r["pass"])
    summary = {
        "scene": "teletubbies-ducks technical validation (show edition)",
        "source": "local_group_orchestration_official_onnx_real_contacts",
        "set": "visual-only decorations (contype=conaffinity=0): sky backdrop, clouds, "
               "sun, vivid grass; duck colors are flat rgba with materials cleared",
        "narration": "macOS Tingting, event-driven (recovery line only after measured "
                     "recovery); no cloud voice, no fabricated events",
        "sim_seconds": round(total_sim, 1),
        "wall_seconds": round(time.monotonic() - started, 1),
        "video": str(final_video) if final_video else None,
        "video_frames": show.frames,
        "passed": passed,
        "total": len(report),
        "beats": report,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    for r in report:
        label = f"{r['beat']:<14}{r.get('member', r.get('pair', ''))}"
        detail = json.dumps(
            {k: v for k, v in r.items() if k not in ("beat", "pass", "member", "pair")},
            ensure_ascii=False)
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {label}  {detail}")
    print(f"\n{passed}/{len(report)} beats passed · sim {summary['sim_seconds']}s · "
          f"wall {summary['wall_seconds']}s · report: {OUT / 'report.json'}")
    if final_video:
        print(f"video ({show.frames} frames @20fps, sim-paced, narrated): {final_video}")


if __name__ == "__main__":
    asyncio.run(main())
