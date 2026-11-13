"""Install immutable, optional functional-scene assets without changing the v8 world.

No training stack, device configuration, or credentials are installed. Sources
and their licenses remain in external/features; large training checkpoints and
videos are deliberately excluded. Re-run safely after an interrupted download.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPOS = {
    "acrobatics": (
        "reble2421/microduck-acrobatics",
        "76cdd4d5b4ce76630a34cc06a3a4b6fc179c438d",
        ["/bench/duckbench/**", "/policies/*.onnx", "/LICENSE", "/README.md"],
    ),
    "tricks-source": (
        "easyrider11/microduck_rl",
        "146777b989f47160d26590e29a9d13957b2c6a3c",
        [
            "/scripts/infer_policy.py",
            "/scripts/eval_roulade_entry.py",
            "/scripts/eval_roller_slalom.py",
            "/scripts/eval_single_blade.py",
            "/src/mjlab_microduck/robot/**",
            "/LICENSE*",
        ],
    ),
    "footstep-runtime": (
        "pollen-robotics/microduck_rl",
        "c992a8cdbf807f934775319e41a72fc310c4a8f3",
        [
            "/scripts/infer_policy.py",
            "/scripts/odom_anchor_sets.json",
            "/src/mjlab_microduck/__init__.py",
            "/src/mjlab_microduck/footsteps.py",
            "/src/mjlab_microduck/footstep_planner.py",
            "/LICENSE*",
        ],
    ),
    "emotions": (
        "pollen-robotics/microduck_emotions",
        "431c73df8a9d3cb6b6067d09ced6c169fdfa59fd",
        ["/keyframes/**", "/sounds/**", "/emotions.json", "/README.md", "/LICENSE*"],
    ),
    "upstream": (
        "pollen-robotics/microduck_rl",
        "bae39f5900b318f7e87fc485c30a31213cfa14eb",
        ["/src/mjlab_microduck/robot/**", "/scripts/infer_policy.py", "/LICENSE*"],
    ),
    "bam": (
        "Rhoban/bam",
        "62bd8ce12154340be97e06f7f41a0ca8f116d967",
        ["/bam/**", "/LICENSE*", "/pyproject.toml"],
    ),
    "playground": (
        "Vottivott/microduck-playground",
        "052a2494dd6372289221c7a4f24a245b443dd75f",
        [
            "/hardware/microdock*/source/**",
            "/hardware/microdock*/sim/**",
            "/hardware/microdock-v2/policy/*.onnx",
            "/src/**",
            "/experiments/desk-climb/source/src/mjlab_microduck/robot/**",
            "/experiments/desk-climb/runtime/**",
            "/experiments/desk-climb/RUNTIME.md",
            "/experiments/desk-climb/evidence/package-smoke-state.json",
            "/experiments/desk-climb/source/scripts/render_ladder_table.py",
            "/scripts/*.py",
            "/integrations/pollen-microduck/**",
            "/LICENSE*",
            "/pyproject.toml",
        ],
    ),
    "step": (
        "bihaokun/microduck-step-up-policy",
        "ec769571438c2558a2d847a164a91022971fceb0",
        [
            "/policies/*.onnx",
            "/manifest.json",
            "/LICENSE*",
            "/NOTICE",
            "/training/microduck_rl_snapshot/src/mjlab_microduck/robot/**",
            "/training/microduck_rl_snapshot/scripts/infer_policy.py",
        ],
    ),
    "circus": (
        "ros-claw/microduck",
        "1034ed000c352476cf213ebe1544eb8c7db8b0e7",
        [
            "/scripts/**",
            "/src/**",
            "/experiments/desk-climb/source/src/mjlab_microduck/robot/**",
            "/experiments/desk-climb/runtime/**",
            "/experiments/desk-climb/RUNTIME.md",
            "/experiments/desk-climb/evidence/package-smoke-state.json",
            "/experiments/desk-climb/source/scripts/render_ladder_table.py",
            "/policies/*.onnx",
            "/training/**/*.py",
            "/training/**/*.onnx",
            "/training/**/*.xml",
            "/training/**/*.json",
            "/LICENSE*",
            "/THIRD_PARTY.md",
        ],
    ),
}
MODELS = {
    "climb": (
        "HannesVonEssen/microduck-climb",
        "15723878fa5cc31e326ce522ab16e25d5142632e",
        ["README.md", "manifest.json", "models/climber.onnx", "models/getup.onnx"],
    ),
    "chimney": (
        "HannesVonEssen/microduck-chimney-climb",
        "1dea21224039f74fb2557456b9bcdec870d96fd7",
        [
            "README.md",
            "manifest.json",
            "config.json",
            "policy.onnx",
            "enter/policy.onnx",
            "exit/policy.onnx",
        ],
    ),
    "tricks": (
        "langli11/microduck-tricks",
        "ae7284e0dc54e6ae10e5f099f4a4d3b93aed7158",
        [
            "README.md",
            "docs/elan_roulade.md",
            "docs/roller_slalom.md",
            "docs/roller_glide.md",
            "policies/roulade_elan_v2_ckpt3750.onnx",
            "policies/roller_slalom_v2_ckpt2000.onnx",
            "policies/roller_glide_short_v15_ckpt1750.onnx",
        ],
    ),
    "terrain_slip": (
        "witcheer/microduck-walk-slip",
        "263a906299ff4f317d47dc9c3a3391aadb1ab06d",
        ["policy.onnx", "manifest.json", "README.md"],
    ),
    "terrain_rough": (
        "witcheer/microduck-walk-rough",
        "b0e4f890eb1f95c2fe210c92de1c95b1eb245cc0",
        ["policy.onnx", "manifest.json", "README.md"],
    ),
    "terrain_step": (
        "witcheer/microduck-walk-step",
        "1ba80ff58c5c9db60e2000f90fdd98e791d42a49",
        ["policy.onnx", "manifest.json", "README.md"],
    ),
    "terrain_stairs": (
        "witcheer/microduck-walk-stairs",
        "a5de4de53ae90763ef94452f7d52d53a28c13fb9",
        ["policy.onnx", "manifest.json", "README.md"],
    ),
    "terrain_gale": (
        "witcheer/microduck-walk-gale",
        "6eeb0a9f0dd6c941dde19420ee0adab9416f4d47",
        ["policy.onnx", "manifest.json", "README.md"],
    ),
    "terrain_slope": (
        "witcheer/microduck-walk-slope",
        "c767098b1af6612c3c9537e0b0ec540866cff8fd",
        ["policy.onnx", "manifest.json", "README.md"],
    ),
    "giant_ball": (
        "witcheer/microduck-kick-right-giant-ball",
        "0a354578e94bf82f08dee674a679862b2dc8caca",
        ["policy.onnx", "manifest.json", "README.md"],
    ),
    "stilts": (
        "HannesVonEssen/microduck-stilts",
        "371b7e0a8843d215afa768439b9e6ceab6248979",
        [
            "config.json",
            "manifest.json",
            "README.md",
            *[
                f"{height}cm/{file}"
                for height in (10, 15, 20, 25, 50, 100, 140, 200)
                for file in ("policy.onnx", "manifest.json")
            ],
        ],
    ),
    "backflip": (
        "HannesVonEssen/microduck-backflip",
        "0aff1c74c8ad3953f331193a5a671257ef5aab37",
        ["policy.onnx", "config.json", "manifest.json", "README.md"],
    ),
    "running": (
        "HannesVonEssen/microduck-running",
        "9f45af1f4b04252f3aa1f4c056fa7fa0d4b35e4c",
        ["policy.onnx", "config.json", "manifest.json", "README.md"],
    ),
    "basketball": (
        "HannesVonEssen/microduck-basketball",
        "6e61a733aeff338bdd352148819bc99cf9a51491",
        ["policy.onnx", "config.json", "manifest.json", "README.md"],
    ),
    "long_jump": (
        "HannesVonEssen/microduck-long-jump",
        "fdcdc787e72b8784bb842159ee70607859cd17ed",
        ["policy.onnx", "config.json", "manifest.json", "README.md"],
    ),
    "circus-base": (
        "pollen-robotics/microduck-policies",
        "283771bcb3690a0a94a288c108365d9b630d21e4",
        ["alpha_stand.onnx", "alpha_walking.onnx", "README.md"],
    ),
    "swing": (
        "HannesVonEssen/microduck-swing",
        "e7a603fa89a74b589608c5a026a7720339cb22e0",
        ["policy.onnx", "config.json", "manifest.json", "README.md"],
    ),
    "hop": (
        "joanfox/microduck-happy-hop",
        "c0447da668255436eea070e862ad8eb89bad2ba1",
        ["policy.onnx", "manifest.json", "README.md"],
    ),
    "flamingo": (
        "RemiFabre/microduck-flamingo-cycle",
        "a69e4f6103a70e355983eb5d4e919da76778a40f",
        ["policy.onnx", "manifest.json", "README.md"],
    ),
    "footsteps": (
        "apirrone/microduck-footsteps",
        "19c38fae6afabddf9c0821009028d0a37963f05f",
        ["footsteps.onnx", "footstepnet.onnx", "README.md"],
    ),
}


def checkout(root, name):
    repo, revision, paths = REPOS[name]
    target = root / name
    if target.exists() and not (target / ".git").exists():
        raise ValueError(f"Refusing to replace existing non-repository directory: {target}")
    if not target.exists():
        subprocess.run(["git", "init", "-q", str(target)], check=True)
        subprocess.run(
            ["git", "-C", str(target), "remote", "add", "origin", f"https://github.com/{repo}.git"],
            check=True,
        )
    git = ["git", "-C", str(target)]
    dirty = subprocess.check_output(git + ["status", "--porcelain"]).strip()
    if dirty:
        raise ValueError(f"Refusing to overwrite modified source: {name}")
    have = subprocess.run(git + ["cat-file", "-e", revision], capture_output=True)
    if have.returncode:
        subprocess.run(
            git + ["fetch", "--depth=1", "--filter=blob:none", "origin", revision], check=True
        )
    subprocess.run(git + ["sparse-checkout", "set", "--no-cone", "--", *paths], check=True)
    subprocess.run(
        git + ["checkout", "--detach", revision],
        check=True,
        env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"},
    )
    return name, {"repository": repo, "revision": revision}


def download(root, name):
    repo, revision, files = MODELS[name]
    target = root / "policies" / name
    target.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for file in files:
        path = target / file
        path.parent.mkdir(parents=True, exist_ok=True)
        # Readiness is revision-bound, never just the presence of a same-named ONNX.
        marker = target / "source.json"
        previous = json.loads(marker.read_text()) if marker.exists() else {}
        if not (
            previous.get("revision") == revision
            and path.exists()
            and hashlib.sha256(path.read_bytes()).hexdigest()
            == previous.get("sha256", {}).get(file)
        ):
            url = f"https://huggingface.co/{repo}/resolve/{revision}/{file}"
            with urllib.request.urlopen(url, timeout=90) as response:
                data = response.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024:
                raise ValueError(f"Policy exceeds size limit: {name}/{file}")
            if not data or data.startswith(b"version https://git-lfs"):
                raise ValueError(f"Incomplete policy download: {name}/{file}")
            temp = path.with_suffix(path.suffix + ".partial")
            temp.write_bytes(data)
            temp.replace(path)
        hashes[file] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {"repository": repo, "revision": revision, "sha256": hashes}
    (target / "source.json").write_text(json.dumps(result, indent=2) + "\n")
    return name, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", choices=[*REPOS, *MODELS])
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="Install pinned CPU helpers into external/features/python",
    )
    args = parser.parse_args()
    root = Path(os.getenv("DUCKKING_SIM_DIR", Path(__file__).resolve().parents[1] / "external"))
    root = root / "features"
    root.mkdir(parents=True, exist_ok=True)
    if args.runtime:
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                sys.executable,
                "--target",
                str(root / "python"),
                "--no-deps",
                "-r",
                str(Path(__file__).with_name("feature_runtime_requirements.txt")),
            ],
            check=True,
        )
    selected = args.only or [*REPOS, *MODELS]
    jobs = [(checkout if name in REPOS else download, name) for name in selected]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(fn, root, name) for fn, name in jobs]
        for future in futures:
            name, result = future.result()
            print(f"Verified {name} @ {result['revision']}", flush=True)


def package_assets(cache, destination):
    """Copy sparse files only after checking their pinned Git blob identities."""

    destination.mkdir(parents=True, exist_ok=True)
    sources = {}
    for name, (repo, revision, _paths) in REPOS.items():
        source = cache / name
        git = ["git", "-C", str(source)]
        if subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip() != revision:
            raise ValueError(f"Wrong source revision: {name}")
        if subprocess.check_output(git + ["status", "--porcelain"]).strip():
            raise ValueError(f"Modified source: {name}")
        # git archive on a partial clone can fetch unrelated trees/attributes.
        # The clean index is pinned to HEAD above; verify each file against its
        # blob identity instead, so this stage needs no network or trust in mtimes.
        for entry in (
            subprocess.check_output(git + ["ls-files", "--stage", "-z"]).decode().split("\0")
        ):
            if not entry:
                continue
            metadata, relative = entry.split("\t", 1)
            mode, oid, stage = metadata.split()
            path = source / relative
            if not path.exists():
                continue  # sparse checkout: intentionally not part of the bundle
            if stage != "0" or mode not in {"100644", "100755"} or path.is_symlink():
                raise ValueError(f"Unsupported functional source entry: {name}/{relative}")
            data = path.read_bytes()
            actual = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
            if actual != oid:
                raise ValueError(f"Source content differs from pinned Git blob: {name}/{relative}")
            target = destination / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(0o755 if mode == "100755" else 0o644)
        sources[name] = {"repository": repo, "revision": revision}
    for name, (repo, revision, files) in MODELS.items():
        target = destination / "policies" / name
        target.mkdir(parents=True)
        source = cache / "policies" / name
        record = json.loads((source / "source.json").read_text())
        if record["revision"] != revision:
            raise ValueError(f"Wrong model revision: {name}")
        for name_ in [*files, "source.json"]:
            data = (source / name_).read_bytes()
            if (
                name_ != "source.json"
                and hashlib.sha256(data).hexdigest() != record["sha256"][name_]
            ):
                raise ValueError(f"Changed model: {name}/{name_}")
            (target / name_).parent.mkdir(parents=True, exist_ok=True)
            (target / name_).write_bytes(data)
        sources["policies/" + name] = {"repository": repo, "revision": revision}
    files = {
        p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(destination.rglob("*"))
        if p.is_file()
    }
    (destination / "sources.json").write_text(
        json.dumps({"sources": sources, "sha256": files}) + "\n"
    )


def verify_package(root):
    """Check source identities and every packaged asset before activating a release."""
    manifest = json.loads((root / "sources.json").read_text())
    expected = {
        name: {"repository": repo, "revision": rev} for name, (repo, rev, _) in REPOS.items()
    }
    expected.update(
        {
            "policies/" + name: {"repository": repo, "revision": rev}
            for name, (repo, rev, _) in MODELS.items()
        }
    )
    if manifest["sources"] != expected:
        raise ValueError("Functional source manifest mismatch")
    for name, checksum in manifest["sha256"].items():
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Invalid functional asset path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Functional asset checksum mismatch: {name}")


if __name__ == "__main__":
    main()
