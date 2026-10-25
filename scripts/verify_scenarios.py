"""Record actual local physics outcomes. Never contacts Linx or a remote server."""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import mujoco
import onnxruntime

from duckking.motion import Action, MotionController
from duckking.simulation import MuJoCoBackend

ROOT = Path(__file__).resolve().parents[1]


async def verify(output: Path):
    backend = MuJoCoBackend(Path(os.environ.get("DUCKKING_SIM_DIR", ROOT / "external")))
    motion = MotionController(backend)
    results = []
    try:
        for name in [
            "sit",
            "stand",
            "kick_left",
            "reset",
            "kick_right",
            "scene_duo",
            "find_companion",
            "collide",
            "chorus",
            "scene_carry",
            "pick_up",
            "carry",
            "put_down",
            "scene_table",
            "table_show",
            "scene_seated",
            "seated_show",
            "scene_skills", "roulade", "ground_pick", "yawn", "idle_on", "idle_off",
            "backward", "strafe_left", "strafe_right", "shake_head", "tilt_head",
            "scene_rollers", "skate", "roller_crouch",
        ]:
            action = Action(name=name)
            await motion.submit(action)
            record = await motion.wait(action.request_id)
            result = {k: record[k] for k in ("name", "status", "outcome", "error") if k in record}
            results.append(result)
            if record["status"] != "completed":
                raise RuntimeError(f"Physics check failed: {name}")
        evidence = {
            "recorded_at": datetime.now(UTC).isoformat(),
            "runtime": "MuJoCo CPU + official ONNX, not robotd",
            "mujoco": mujoco.__version__,
            "onnxruntime": onnxruntime.__version__,
            "model_commit": "b02fdea4902c2b93b7d34a83a6f05da4ececb7d3",
            "policy_commit": "665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448",
            "ball": {"radius_m": 0.035, "mass_kg": 0.015, "placement": "before each selected foot"},
            "grasp": {
                "model": "experimental_beak_contact_v1",
                "object_mass_kg": 0.004,
                "object_size_m": [0.020, 0.130, 0.008],
                "attachment": "contact_and_friction_only",
                "hardware_calibrated": False,
            },
            "control_hz": 50,
            "physics_timestep_s": 0.005,
            "chorus": "Local synthesized score; this script verifies control, not speaker output",
            "results": results,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            output.write_text, json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
        )
        print(f"Verified {len(results)} actions; evidence saved to {output}")
    finally:
        await motion.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".duckking/physics-scenes.json"))
    asyncio.run(verify(parser.parse_args().output))
