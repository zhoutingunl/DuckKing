"""Render LIVE official MuJoCo telemetry, without copying upstream models into this repo.

Run using microduck_rl's Python, which provides mujoco/numpy. The physical world keeps
running in the upstream body server; this process only reads its state for rendering.
"""

import argparse
import json
import math
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen

import mujoco

JOINTS = (
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll", "mouth",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rl-root", type=Path, required=True)
    parser.add_argument("--api-port", type=int, default=8767)
    parser.add_argument("--body-port", type=int, default=7801)
    parser.add_argument("--sequence", choices=["basic", "choreography"], default="basic")
    parser.add_argument("--output", type=Path, default=Path("docs/media/official-simulation.mp4"))
    args = parser.parse_args()
    api = f"http://127.0.0.1:{args.api_port}"

    def request(path, body=None):
        req = Request(api + path, data=json.dumps(body).encode() if body else None,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=5) as response:
            return json.load(response)

    if request("/api/health")["backend"] != "robotd":
        raise SystemExit("This recording requires the real robotd adapter, not preview")
    request("/api/state")  # Start the official telemetry subscription.
    model_path = args.rl_root / "src/mjlab_microduck/robot/microduck/scene.xml"
    model = mujoco.MjModel.from_xml_path(str(model_path))
    model.vis.global_.offwidth, model.vis.global_.offheight = 960, 720
    data = mujoco.MjData(model)
    base = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "trunk_base_freejoint")
    base_address = model.jnt_qposadr[base]
    mapping = []
    for index, name in enumerate(JOINTS):
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint >= 0:
            mapping.append((index, model.jnt_qposadr[joint]))
    camera = mujoco.MjvCamera()
    camera.distance, camera.azimuth, camera.elevation = .58, 135, -18
    renderer = mujoco.Renderer(model, height=720, width=960)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoder = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", "960x720", "-r", "20", "-i", "-", "-an", "-c:v", "libx264",
        "-crf", "22", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags",
        "+faststart", str(args.output)], stdin=subprocess.PIPE)
    schedule = [(2, {"name": "nod"}), (5, {"name": "walk"}),
                (8, {"name": "turn_left"}), (10, {"name": "walk", "duration": 3}),
                (12, {"name": "stop"})]
    if args.sequence == "choreography":
        schedule = [(1, {"name": "flash_step"}), (5, {"name": "bear_shake"}),
                    (9, {"name": "flash_step"}), (10.3, {"name": "stop"})]
    actions, observations = [], []
    with socket.create_connection(("127.0.0.1", args.body_port), timeout=2) as connection:
        stream = connection.makefile("rwb")
        try:
            started = time.monotonic()
            for frame_index in range(300):
                elapsed = frame_index / 20
                while schedule and elapsed >= schedule[0][0]:
                    _, command = schedule.pop(0)
                    actions.append(request("/api/actions", command))
                stream.write(b'{"op":"read"}\n')
                stream.flush()
                state = json.loads(stream.readline())
                data.qpos[base_address:base_address + 3] = state["trunk"]
                data.qpos[base_address + 3:base_address + 7] = state["imu"]["quat"]
                for wire_index, address in mapping:
                    data.qpos[address] = state["positions"][wire_index]
                mujoco.mj_forward(model, data)
                camera.lookat[:] = state["trunk"]
                camera.lookat[2] += .035
                renderer.update_scene(data, camera)
                encoder.stdin.write(renderer.render().tobytes())
                if frame_index % 10 == 0:
                    observations.append({"t": elapsed, "trunk": state["trunk"],
                                         "gravity": state["imu"]["gravity"],
                                         "head": state["positions"][5:9], "sim_time": state["sim_time"]})
                time.sleep(max(0, started + (frame_index + 1) / 20 - time.monotonic()))
        finally:
            request("/api/actions", {"name": "stop"})
            encoder.stdin.close()
            encoder.wait(timeout=30)
            renderer.close()
    if encoder.returncode:
        raise SystemExit("Video encoding failed")
    result = {
        "tested_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "source": "live official robotd + MuJoCo body state, re-rendered with official scene",
        "sequence": args.sequence,
        "capture_wall_seconds": time.monotonic() - started,
        "cloud_voice_tested": False,
        "actions": [request(f"/api/actions/{action['id']}") for action in actions],
        "observations": observations,
        "net_displacement_m": math.dist(observations[0]["trunk"][:2], observations[-1]["trunk"][:2]),
        "final_backend": request("/api/state")["backend"],
    }
    # Telemetry includes robot geometry but no credentials. Keep the report compact.
    telemetry = result["final_backend"].pop("telemetry", {}) or {}
    result["final_backend"]["telemetry_summary"] = {
        key: telemetry.get(key) for key in ["policy", "safety", "loop", "move"]}
    args.output.with_suffix(".json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({"video": str(args.output), "displacement_m": result["net_displacement_m"]}))


if __name__ == "__main__":
    main()
