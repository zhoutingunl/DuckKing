"""CPU PPO for the passive seesaw. Run with PYTHONPATH=src; see SEESAW_COACH.md."""

import argparse
import hashlib
import json
import platform
import signal
import time
from pathlib import Path

import gymnasium as gym
import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback

from duckking.seesaw import SeesawWorld
from duckking.seesaw_policy import SeesawPolicy


def write(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


class Env(gym.Env):
    def __init__(self, assets, seed):
        self.world = SeesawWorld(assets)
        self.next_seed = 100000 + seed * 10000
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, (14,), dtype=np.float32)
        self.action_space = gym.spaces.Discrete(3)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.next_seed += 1
        return self.world.reset(self.next_seed), {}

    def step(self, action):
        obs, r, done, truncated, info = self.world.step(int(action))
        return obs, r * 0.1, done, truncated, info


def export(model, world, path):
    layers = [m for m in model.policy.mlp_extractor.policy_net if isinstance(m, torch.nn.Linear)]
    layers.append(model.policy.action_net)
    write(
        path,
        {
            **world.manifest(),
            "steps": model.num_timesteps + getattr(model, "initial_steps", 0),
            "layers": [
                {"weight": m.weight.detach().cpu().tolist(), "bias": m.bias.detach().cpu().tolist()}
                for m in layers
            ],
        },
    )
    policy = SeesawPolicy(path, world.manifest())
    for obs in np.random.default_rng(89).normal(size=(32, 14)).astype(np.float32):
        assert policy(obs) == int(model.predict(obs, deterministic=True)[0])
    return policy


def warm_start(model, path, world):
    """Curriculum transfer of the task actor, not imitation or a rule policy.

    The old 12 observations keep their meanings. Two new bookkeeping inputs get
    zero weights. The value network and optimizer start afresh, recorded below.
    """
    raw = path.read_bytes()
    payload = json.loads(raw)
    if (
        payload.get("contract") != "seesaw-v1-discrete"
        or payload.get("model_sha256") != world.fingerprint
        or payload.get("action_type") != "categorical"
        or type(payload.get("steps")) is not int
        or payload["steps"] <= 0
    ):
        raise ValueError("仅支持同一物理模型的第一阶段任务 PPO 工件")
    layers = [m for m in model.policy.mlp_extractor.policy_net if isinstance(m, torch.nn.Linear)]
    layers.append(model.policy.action_net)
    if len(payload["layers"]) != len(layers):
        raise ValueError("预训练任务网络结构无效")
    width = 12
    with torch.no_grad():
        for source, target in zip(payload["layers"], layers, strict=True):
            w, b = np.asarray(source["weight"], np.float32), np.asarray(source["bias"], np.float32)
            if (
                w.shape != (target.out_features, width)
                or b.shape != (target.out_features,)
                or not np.isfinite(w).all()
                or not np.isfinite(b).all()
            ):
                raise ValueError("预训练任务权重无效")
            target.weight.zero_()
            target.weight[:, :width].copy_(torch.from_numpy(w))
            target.bias.copy_(torch.from_numpy(b))
            width = target.out_features
    model.initial_steps = payload["steps"]
    return {
        "kind": "curriculum_task_ppo",
        "source_contract": payload["contract"],
        "source_steps": payload["steps"],
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "new_inputs": "hold and time, initialized with zero actor weights",
        "critic_and_optimizer": "new, not transferred",
    }


def evaluate(world, policy, seeds, cancelled=lambda: False):
    rows = []
    for seed in seeds:
        if cancelled():
            raise InterruptedError("评估已取消")
        obs, total = world.reset(seed), 0
        while not world.done:
            if cancelled():
                raise InterruptedError("评估已取消")
            obs, reward, _, _, info = world.step(policy(obs))
            total += reward
        rows.append(
            {
                "seed": seed,
                "success": info["success"],
                "reason": info["reason"],
                "seconds": info["seconds"],
                "return": total,
                "angle_deg": info["angle_deg"],
                "position_m": info["position_m"],
                "hold_seconds": info["hold_seconds"],
                "mean_abs_angle_deg": info["mean_abs_angle_deg"],
            }
        )
    n, wins = len(rows), sum(r["success"] for r in rows)
    p, z = wins / n, 1.96
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return {
        "episodes": n,
        "successes": wins,
        "success_rate": p,
        "ci95": [center - half, center + half],
        "results": rows,
        "mean_return": float(np.mean([r["return"] for r in rows])),
        "mean_abs_angle_deg": float(np.mean([r["mean_abs_angle_deg"] for r in rows])),
    }


class Recorder(BaseCallback):
    def __init__(self, directory, world, report, started):
        super().__init__()
        self.directory, self.world, self.report, self.started = directory, world, report, started
        self.best, self.streak = (-1, -float("inf")), 0
        self.cancelled = False

    def record(self, row):
        row = {"steps": self.num_timesteps, "elapsed_s": time.perf_counter() - self.started, **row}
        self.report["metrics"].append(row)
        self.report.update(steps=self.num_timesteps, elapsed_s=row["elapsed_s"])
        write(self.directory / "report.json", self.report)
        print(json.dumps(row), flush=True)

    def _on_step(self):
        if self.cancelled:
            return False
        if self.num_timesteps % 8192 == 0:
            policy = export(self.model, self.world, self.directory / "latest.json")
            result = evaluate(self.world, policy, range(20000, 20020), lambda: self.cancelled)
            self.streak = self.streak + 1 if result["success_rate"] >= 0.9 else 0
            score = (result["success_rate"], result["mean_return"])
            if score > self.best:
                self.best = score
                export(self.model, self.world, self.directory / "policy.json")
                self.report["selected_steps"] = policy.steps
                self.report["selected_phase_steps"] = self.num_timesteps
            if self.streak >= 2 and not self.report.get("converged_at"):
                self.report["converged_at"] = {
                    "steps": self.num_timesteps,
                    "elapsed_s": time.perf_counter() - self.started,
                }
            self.record(
                {"kind": "validation", **{k: v for k, v in result.items() if k != "results"}}
            )
        elif self.num_timesteps % 1024 == 0:
            values = {
                k.removeprefix("train/"): float(v)
                for k, v in self.model.logger.name_to_value.items()
                if k.startswith("train/") and np.isscalar(v) and np.isfinite(v)
            }
            info = self.locals["infos"][0]
            self.record(
                {
                    "kind": "update",
                    "optimizer": values,
                    "sample": {
                        k: info[k]
                        for k in (
                            "position_m",
                            "angle_deg",
                            "angular_speed_deg_s",
                            "reward_terms",
                            "hold_seconds",
                        )
                    },
                }
            )
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=Path, default=Path("external"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=65536)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--warm-start", type=Path)
    args = parser.parse_args()
    if args.steps < 8192 or args.steps > 1048576 or args.steps % 8192:
        parser.error("steps must be a multiple of 8192, at most 1048576")
    if not 0 <= args.seed <= 9999:
        parser.error("seed must be between 0 and 9999")
    args.output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.perf_counter()
    env, evaluation = Env(args.assets, args.seed), SeesawWorld(args.assets)
    params = dict(
        n_steps=1024,
        batch_size=64,
        n_epochs=5,
        learning_rate=0.0003,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=0.01,
        clip_range=0.2,
    )
    model = PPO("MlpPolicy", env, seed=args.seed, device="cpu", verbose=0, **params)
    initialization = (
        warm_start(model, args.warm_start, evaluation)
        if args.warm_start
        else {"kind": "random_task_actor", "source_steps": 0}
    )
    report = {
        "phase": "training",
        "steps": 0,
        "seed": args.seed,
        "budget_steps": args.steps,
        "manifest": env.world.manifest(),
        "hyperparameters": params,
        "device": "cpu",
        "workers": 1,
        "torch_threads": 1,
        "platform": platform.platform(),
        "metrics": [],
        "elapsed_s": 0,
        "train_seed_start": env.next_seed,
        "validation_seeds": [20000, 20019],
        "test_seeds": [30000, 30099],
        "reward_scale": 0.1,
        "initialization": initialization,
        "gate": "two consecutive validations >=18/20; final held-out test is separate",
    }
    export(model, evaluation, args.output / "early.json")
    recorder = Recorder(args.output, evaluation, report, started)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: setattr(recorder, "cancelled", True))
    write(args.output / "report.json", report)
    try:
        initial = evaluate(
            evaluation,
            SeesawPolicy(args.output / "early.json", evaluation.manifest()),
            range(20000, 20020),
            lambda: recorder.cancelled,
        )
        recorder.best = (initial["success_rate"], initial["mean_return"])
        initial_policy = export(model, evaluation, args.output / "policy.json")
        report.update(selected_steps=initial_policy.steps, selected_phase_steps=0)
        recorder.record(
            {"kind": "validation", **{k: v for k, v in initial.items() if k != "results"}}
        )
        model.learn(args.steps, callback=recorder)
        export(model, evaluation, args.output / "latest.json")
        if recorder.cancelled:
            report["phase"] = "cancelled"
        else:
            report["phase"] = "testing"
            report["test_stage"] = "ppo"
            write(args.output / "report.json", report)
            policy = SeesawPolicy(args.output / "policy.json", evaluation.manifest())
            report["test"] = evaluate(
                evaluation, policy, range(30000, 30100), lambda: recorder.cancelled
            )
            report.update(test_stage="baseline", elapsed_s=time.perf_counter() - started)
            write(args.output / "report.json", report)
            report["baseline_test"] = evaluate(
                evaluation, lambda _: 0, range(30000, 30100), lambda: recorder.cancelled
            )
            report.update(test_stage="rule", elapsed_s=time.perf_counter() - started)
            write(args.output / "report.json", report)
            report["rule_test"] = evaluate(
                evaluation, SeesawWorld.rule_action, range(30000, 30100), lambda: recorder.cancelled
            )
            report["phase"] = "completed"
            report["test_stage"] = "completed"
    except InterruptedError:
        report["phase"] = "cancelled"
    except Exception as exc:
        report.update(phase="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        report.update(steps=model.num_timesteps, elapsed_s=time.perf_counter() - started)
        write(args.output / "report.json", report)


if __name__ == "__main__":
    main()
