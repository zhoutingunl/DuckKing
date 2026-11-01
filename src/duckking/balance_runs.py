"""Bounded read access to local training evidence, and opt-in CPU jobs."""

import asyncio
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


class BalanceRuns:
    def __init__(self, root, bundled):
        self.root, self.bundled = Path(root), Path(bundled)
        self.process = None
        self.active_id = None
        self.log = None
        self.watcher = None
        self.cancel_requested = set()
        self.lock = asyncio.Lock()

    def directory(self, run):
        if not isinstance(run, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", run):
            raise ValueError("无效训练记录编号")
        for root in (self.root, self.bundled):
            directory = root / run
            if directory.is_dir() and not directory.is_symlink():
                return directory
        raise ValueError("训练记录不存在")

    def list(self):
        records, seen = [], set()
        for root in (self.root, self.bundled):
            if not root.is_dir():
                continue
            for directory in sorted(root.iterdir(), reverse=True):
                if directory.name in seen or directory.is_symlink() or not directory.is_dir():
                    continue
                seen.add(directory.name)
                status = read_json(directory / "status.json")
                if status:
                    manifest = read_json(directory / "manifest.json") or {}
                    records.append(
                        {
                            "id": directory.name,
                            **status,
                            "contract": manifest.get("contract"),
                            "record_updated_at": directory.stat().st_mtime,
                        }
                    )
        return sorted(records, key=lambda row: row["record_updated_at"], reverse=True)[:100]

    def details(self, run):
        directory = self.directory(run)
        rows = []
        path = directory / "metrics.jsonl"
        if path.exists():
            # At most 2M steps / 256 steps/update; tolerate an unfinished final line.
            for line in path.read_text().splitlines()[-10000:]:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return {
            "id": run,
            "status": read_json(directory / "status.json"),
            "manifest": read_json(directory / "manifest.json"),
            "metrics": rows,
            "baseline": read_json(directory / "baseline.json"),
            "test": read_json(directory / "test.json"),
            "baseline_test": read_json(directory / "baseline-test.json"),
        }

    def policy(self, level, run=None, checkpoint="trained", contract=None):
        if checkpoint not in {"trained", "early"}:
            raise ValueError("无效策略版本")
        if run is None:
            candidates = [
                r
                for r in self.list()
                if r.get("level") == level
                and (contract is None or r.get("contract") == contract)
                and (self.directory(r["id"]) / "best-policy.json").exists()
            ]
            if not candidates:
                raise ValueError("本关尚无已评估的 PPO 策略；可明确选择官方基线")
            run = candidates[0]["id"]
        directory = self.directory(run)
        file = directory / ("policy-0.json" if checkpoint == "early" else "best-policy.json")
        if not file.is_file():
            raise ValueError("所选策略尚未生成，训练过程中可先查看曲线")
        return file, run

    @property
    def enabled(self):
        return os.getenv("DUCKKING_BALANCE_TRAINING") == "1"

    async def launch(self, level, steps, seed, assets):
        if not self.enabled:
            raise ValueError("本服务只展示训练记录；管理员可显式启用独立 CPU 训练进程")
        if level not in (1, 2, 3) or steps not in (16384, 65536, 131072) or not 0 <= seed < 10000:
            raise ValueError("无效训练参数")
        async with self.lock:
            if self.process and self.process.returncode is None:
                raise ValueError("已有训练任务运行；请等待完成或先取消")
            if self.log:
                self.log.close()
            self.root.mkdir(parents=True, exist_ok=True)
            run = f"level{level}-{time.time_ns()}"
            directory = self.root / run
            directory.mkdir()
            self.log = await asyncio.to_thread((directory / "worker.log").open, "wb")
            status_path = directory / "status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "phase": "preparing",
                        "level": level,
                        "budget_steps": steps,
                        "steps": 0,
                        "elapsed_s": 0,
                        "seed": seed,
                        "device": "cpu",
                        "converged_at": None,
                    }
                )
            )
            executable = os.getenv("DUCKKING_TRAIN_PYTHON", sys.executable)
            env = {
                **os.environ,
                "PYTHONPATH": str(SOURCE_ROOT),
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
            }
            try:
                self.process = await asyncio.create_subprocess_exec(
                    executable,
                    str(SOURCE_ROOT.parent / "training/train_balance.py"),
                    "--assets",
                    str(assets),
                    "--output",
                    str(directory),
                    "--level",
                    str(level),
                    "--steps",
                    str(steps),
                    "--seed",
                    str(seed),
                    "--envs",
                    "2",
                    env=env,
                    stdout=self.log,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=True,
                )
            except OSError:
                self.log.close()
                status = read_json(status_path) or {}
                status.update(phase="failed", error="无法启动训练解释器")
                status_path.write_text(json.dumps(status, ensure_ascii=False))
                raise ValueError("无法启动训练解释器，请按训练文档安装独立环境") from None
            self.active_id = run
            self.watcher = asyncio.create_task(self._watch(self.process, directory))
            return {"id": run, "phase": "preparing", "device": "cpu"}

    async def _watch(self, process, directory):
        code = await process.wait()
        status = read_json(directory / "status.json") or {}
        if status.get("phase") not in {"failed", "cancelled", "completed"}:
            # Cancellation can arrive while Python is importing Torch, before
            # the training CLI has installed its cooperative signal handler.
            if directory.name in self.cancel_requested and code == -signal.SIGTERM:
                status.update(phase="cancelled")
            else:
                status.update(phase="failed", error=f"训练进程退出（{code}）；请查看管理员日志")
            (directory / "status.json").write_text(json.dumps(status, ensure_ascii=False))
        self.cancel_requested.discard(directory.name)

    async def cancel(self, run):
        async with self.lock:
            if run != self.active_id or self.process is None or self.process.returncode is not None:
                raise ValueError("该记录不是本服务当前运行的任务")
            self.cancel_requested.add(run)
            self.process.terminate()
            return {"id": run, "phase": "cancelling"}

    async def close(self):
        if self.process and self.process.returncode is None:
            self.cancel_requested.add(self.active_id)
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 15)
            except TimeoutError:
                # A stuck sampler must not leave its CPU child workers orphaned.
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await self.process.wait()
        if self.log:
            self.log.close()
        if self.watcher:
            await self.watcher
