"""Fetch pinned public scene assets; never copy private runtime or device files."""

import hashlib
import os
import subprocess
import urllib.request
from pathlib import Path

REVISION = "b02fdea4902c2b93b7d34a83a6f05da4ececb7d3"
POLICIES = "665ae4eb20bfe13bca1ef4ea6d4bb6b4a096e448"
CHECKSUMS = {
    "alpha_sitstand.onnx": "a6f102d9fd655782ba85bfffe18175c34621da719cffcdd673be7982a06fc254",
    "manifest.json": "c566390738dd90a54c1e2de829aaab0e904c636949e2c2c6158ee7bbb889b818",
    "velstand.onnx": "2fc7f8ee6acd7d0d3f66a99927b5d5a56589aeed02ec714de329b252d5ccf492",
    "ball_kick_left.onnx": "d6928284dccd3dd61e08bf2f760effa74309fbefd97b2b31afb2a60f526d196a",
    "ball_kick_right.onnx": "147a32c388c6b19111b3ac3b550a9a6dc8b8bf267118af4d8c3712522eedb5af",
}


def main():
    root = Path(
        os.environ.get("DUCKKING_SIM_DIR", Path(__file__).resolve().parents[1] / "external")
    )
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "microduck_rl"
    if not repo.exists():
        subprocess.run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "https://github.com/pollen-robotics/microduck_rl.git",
                str(repo),
            ],
            check=True,
        )
    if (repo / "pyproject.toml").exists() and subprocess.check_output(
        ["git", "-C", str(repo), "status", "--porcelain"]
    ).strip():
        raise SystemExit("Refusing to overwrite modified upstream checkout")
    subprocess.run(["git", "-C", str(repo), "checkout", REVISION], check=True)
    policies = root / "policies"
    policies.mkdir(exist_ok=True)
    for name, checksum in CHECKSUMS.items():
        path = policies / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == checksum:
            continue
        url = f"https://huggingface.co/pollen-robotics/microduck-policies/resolve/{POLICIES}/{name}"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != checksum:
            raise SystemExit(f"Checksum mismatch: {name}")
        path.write_bytes(data)
    print("Official model and policies verified; licenses remain in the external checkout.")


if __name__ == "__main__":
    main()
