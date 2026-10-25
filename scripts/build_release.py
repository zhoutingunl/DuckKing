"""Build an immutable release from a Git commit; never package the working tree."""

import argparse
import getpass
import hashlib
import io
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def commit_history(commit: str):
    output = subprocess.check_output(
        ["git", "log", "--topo-order", "--max-count=2000", "--format=%H%x09%P%x09%s", commit],
        cwd=ROOT, text=True,
    )
    rows = []
    for line in output.splitlines():
        sha, parents, subject = line.split("\t", 2)
        rows.append({"commit": sha, "parents": parents.split(), "subject": subject[:300]})
    return rows


def build(ref: str, version: str, output: Path, coverage_summaries=()):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", version):
        raise ValueError("Invalid release version")
    commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", ref + "^{commit}"], cwd=ROOT, text=True
    ).strip()
    source = subprocess.check_output(["git", "archive", commit], cwd=ROOT)
    # Reports are supplied from completed CI artifacts; never guess from a stale
    # local coverage.json or apply the current report to historical deployments.
    from duckking.release_coverage import public_coverage

    reports = []
    for path in coverage_summaries:
        report = public_coverage(json.loads(path.read_text()))
        if report is None:
            raise ValueError("Invalid coverage summary")
        reports.append(report)
    metadata = dict(
        version=version,
        commit=commit,
        git_ref=ref,
        target="yzh737",
        built_at=datetime.now(UTC).isoformat(),
        operator=getpass.getuser(),
    )
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / f"duckking-{version}.tar.gz"
    if artifact.exists():
        raise FileExistsError("Refusing to overwrite a release artifact")
    with tempfile.TemporaryDirectory(prefix="duckking-release-") as directory:
        tree = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(source)) as archive:
            archive.extractall(tree, filter="data")
        subprocess.run(["npm", "ci"], cwd=tree / "frontend", check=True)
        subprocess.run(["npm", "run", "build"], cwd=tree / "frontend", check=True)
        fetcher = tree / "scripts/fetch_scene_assets.py"
        upstream = runpy.run_path(str(fetcher))
        cache = ROOT / "external"
        subprocess.run(
            [sys.executable, str(fetcher)],
            check=True,
            env=os.environ | {"DUCKKING_SIM_DIR": str(cache)},
        )
        assets = tree / "external"
        assets.mkdir()
        # Archive the pinned upstream commit, excluding its .git and any working files.
        model_source = subprocess.check_output(
            ["git", "-C", str(cache / "microduck_rl"), "archive", upstream["REVISION"]]
        )
        with tarfile.open(fileobj=io.BytesIO(model_source)) as archive:
            archive.extractall(assets / "microduck_rl", filter="data")
        (assets / "policies").mkdir()
        for name, expected in upstream["CHECKSUMS"].items():
            policy = cache / "policies" / name
            assert hashlib.sha256(policy.read_bytes()).hexdigest() == expected
            shutil.copyfile(policy, assets / "policies" / name)
        (assets / "sources.json").write_text(
            json.dumps(
                {
                    "model_commit": upstream["REVISION"],
                    "policy_commit": upstream["POLICIES"],
                }
            )
            + "\n"
        )
        asr_fetcher = tree / "scripts/fetch_asr_assets.py"
        subprocess.run(
            [sys.executable, str(asr_fetcher)], check=True,
            env=os.environ | {"DUCKKING_ASR_MODEL_DIR": str(cache / "asr")},
        )
        shutil.copytree(cache / "asr", assets / "asr", ignore=shutil.ignore_patterns('test_wavs'))
        (tree / "release.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
        )
        (tree / "release-commits.json").write_text(
            json.dumps(commit_history(commit), ensure_ascii=False) + "\n"
        )
        (tree / "release-coverage.json").write_text(json.dumps(reports) + "\n")
        with tarfile.open(artifact, "w:gz") as archive:
            # Only tracked sources, a freshly built frontend, and public release metadata.
            paths = (
                subprocess.check_output(
                    ["git", "ls-tree", "-r", "--name-only", "-z", commit], cwd=ROOT
                )
                .decode()
                .split("\0")
            )
            for name in filter(None, paths):
                archive.add(tree / name, arcname=name, recursive=False)
            archive.add(tree / "frontend/dist", arcname="frontend/dist")
            archive.add(assets, arcname="external")
            archive.add(tree / "release.json", arcname="release.json")
            archive.add(tree / "release-commits.json", arcname="release-commits.json")
            archive.add(tree / "release-coverage.json", arcname="release-coverage.json")
    checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = artifact.with_suffix(".sha256")
    manifest.write_text(f"{checksum}  {artifact.name}\n")
    print(
        json.dumps({"artifact": str(artifact), "sha256": checksum, **metadata}, ensure_ascii=False)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / ".duckking/releases")
    parser.add_argument("--coverage-summary", type=Path, action="append", default=[])
    args = parser.parse_args()
    build(args.ref, args.version, args.output, args.coverage_summary)
