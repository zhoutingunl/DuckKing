"""CPU-only PPO training CLI. Records are measurements, never generated curves.

Run in training/requirements.txt's isolated environment with PYTHONPATH=src.
"""

import argparse
import hashlib
import json
import os
import platform
import signal
import threading
import time
from collections import defaultdict
from pathlib import Path

import gymnasium as gym
import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import SubprocVecEnv

from duckking.balance import BalanceConfig, BalanceWorld
from duckking.balance_policy import BalancePolicy

WRITE_LOCK = threading.Lock()


def atomic_json(path, data):
    with WRITE_LOCK:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8"
        )
        temporary.replace(path)


class BalanceEnv(gym.Env):
    def __init__(self, assets, level, seed, reward_scale=0.05):
        self.world = BalanceWorld(assets, BalanceConfig(level=level))
        self.next_seed = seed
        self.reward_scale = reward_scale
        self.observation_space = gym.spaces.Box(
            -np.inf, np.inf, (len(self.world.observation()),), dtype=np.float32
        )
        self.action_space = gym.spaces.Box(-1.0, 1.0, (3,), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self.next_seed = seed
        self.next_seed += 1
        return self.world.reset(self.next_seed), {}

    def step(self, action):
        obs, reward, terminated, truncated, info = self.world.step(action)
        return obs, reward * self.reward_scale, terminated, truncated, info


def export(model, world, path):
    layers = [m for m in model.policy.mlp_extractor.policy_net if isinstance(m, torch.nn.Linear)]
    layers.append(model.policy.action_net)
    atomic_json(
        path,
        {
            "contract": world.manifest()["contract"],
            "model_sha256": world.fingerprint,
            "level": world.config.level,
            "steps": model.num_timesteps,
            "layers": [
                {"weight": m.weight.detach().cpu().tolist(), "bias": m.bias.detach().cpu().tolist()}
                for m in layers
            ],
        },
    )
    # Check the actual exported artifact, including clipping and tanh activations.
    policy = BalancePolicy(path, world.manifest())
    rng = np.random.default_rng(79)
    for _ in range(32):
        obs = rng.normal(size=world.manifest()["observation_size"]).astype(np.float32)
        expected, _ = model.predict(obs, deterministic=True)
        np.testing.assert_allclose(policy(obs), expected, rtol=1e-5, atol=2e-6)


def evaluate(world, policy, seeds, cancelled=lambda: False):
    results = []
    for seed in seeds:
        if cancelled():
            return None
        obs = world.reset(seed)
        reward = 0.0
        while not world.done:
            if cancelled():
                return None
            obs, r, _, _, info = world.step(policy(obs))
            reward += r
        results.append(
            {
                "seed": seed,
                "success": info["success"],
                "reason": info["reason"],
                "return": reward,
                "seconds": info["seconds"],
                "radius": info["radius"],
                "heading_fraction": info["heading_fraction"],
                "mean_slip": info["mean_slip"],
            }
        )
    wins, n = sum(r["success"] for r in results), len(results)
    p, z = wins / n, 1.96
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return {
        "episodes": n,
        "successes": wins,
        "success_rate": p,
        "ci95": [center - half, center + half],
        "mean_return": float(np.mean([r["return"] for r in results])),
        "results": results,
    }


class Recorder(BaseCallback):
    def __init__(self, world, directory, status, started, eval_every, cancelled):
        super().__init__()
        self.world, self.directory, self.status = world, directory, status
        self.started, self.eval_every, self.cancelled = started, eval_every, cancelled
        self.last_eval, self.last_row, self.streak = 0, -1, 0
        self.sums, self.count = defaultdict(float), 0

    def write(self, record):
        row = {
            "steps": self.num_timesteps,
            "elapsed_s": time.perf_counter() - self.started,
            **record,
        }
        with (self.directory / "metrics.jsonl").open("a") as f:
            f.write(json.dumps(row, allow_nan=False) + "\n")
        self.status.update(steps=self.num_timesteps, elapsed_s=row["elapsed_s"])
        atomic_json(self.directory / "status.json", self.status)

    def _on_step(self):
        for info in self.locals["infos"]:
            self.count += 1
            for key, value in info["reward_terms"].items():
                self.sums["reward/" + key] += value
            for key in ("radius", "slip", "upright", "rpm"):
                self.sums["physics/" + key] += info[key]
        return not self.cancelled()

    def _on_rollout_start(self):
        if not self.num_timesteps or self.last_row == self.num_timesteps:
            return
        self.last_row = self.num_timesteps
        row = {key: float(v / self.count) for key, v in self.sums.items()}
        row.update(
            {
                k: float(v)
                for k, v in self.model.logger.name_to_value.items()
                if k.startswith("train/") and np.isscalar(v) and np.isfinite(v)
            }
        )
        row["parameters/actor_l2"] = float(
            torch.sqrt(
                sum(
                    (p.detach() ** 2).sum()
                    for p in self.model.policy.mlp_extractor.policy_net.parameters()
                )
            )
        )
        row["parameters/action_std"] = float(self.model.policy.log_std.exp().mean().detach())
        self.sums.clear()
        self.count = 0
        self.write({"kind": "update", **row})
        if self.num_timesteps - self.last_eval < self.eval_every or self.cancelled():
            return
        self.last_eval = self.num_timesteps
        self.status["phase"] = "evaluating"
        atomic_json(self.directory / "status.json", self.status)
        path = self.directory / f"policy-{self.num_timesteps}.json"
        export(self.model, self.world, path)
        result = evaluate(
            self.world,
            BalancePolicy(path, self.world.manifest()),
            range(1_000_000, 1_000_020),
            self.cancelled,
        )
        if result is None:
            return
        atomic_json(self.directory / f"validation-{self.num_timesteps}.json", result)
        self.streak = self.streak + 1 if result["success_rate"] >= 0.90 else 0
        if self.streak >= 2 and self.status.get("converged_at") is None:
            self.status["converged_at"] = {
                "steps": self.num_timesteps,
                "elapsed_s": time.perf_counter() - self.started,
            }
        if result["success_rate"] >= self.status.get("best_success_rate", -1):
            self.status["best_success_rate"] = result["success_rate"]
            self.status["best_steps"] = self.num_timesteps
            atomic_json(self.directory / "best-policy.json", json.loads(path.read_text()))
            self.model.save(self.directory / "checkpoint")
        self.write({"kind": "validation", **{k: v for k, v in result.items() if k != "results"}})
        self.status["phase"] = "training"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=Path, default=Path("external"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--level", type=int, choices=[1, 2, 3], required=True)
    parser.add_argument("--steps", type=int, default=131072)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--envs", type=int, default=4)
    parser.add_argument("--eval-every", type=int, default=8192)
    parser.add_argument("--test-episodes", type=int, default=100)
    parser.add_argument("--reward-scale", type=float, default=0.05)
    parser.add_argument("--initial-std", type=float, default=0.6)
    args = parser.parse_args()
    if not 1024 <= args.steps <= 2_000_000 or not 1 <= args.envs <= 4:
        parser.error("steps must be 1024–2000000; envs must be 1–4")
    if not 1 <= args.test_episodes <= 1000 or args.eval_every < 1024:
        parser.error("invalid evaluation bounds")
    if not 0.001 <= args.reward_scale <= 1 or not 0.05 <= args.initial_std <= 1:
        parser.error("invalid optimization reward scale / exploration standard deviation")
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "manifest.json").exists():
        parser.error("output already contains a run; use a new directory")
    torch.set_num_threads(1)
    cancelled = False

    def cancel(*_):
        nonlocal cancelled
        cancelled = True

    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    started = time.perf_counter()
    status = {
        "phase": "preparing",
        "level": args.level,
        "seed": args.seed,
        "steps": 0,
        "budget_steps": args.steps,
        "elapsed_s": 0,
        "device": "cpu",
        "converged_at": None,
    }
    atomic_json(args.output / "status.json", status)
    finished = threading.Event()

    def heartbeat():
        while not finished.wait(2):
            status["elapsed_s"] = time.perf_counter() - started
            atomic_json(args.output / "status.json", dict(status))

    heart = threading.Thread(target=heartbeat, daemon=True)
    heart.start()
    vector = None
    try:
        world = BalanceWorld(args.assets, BalanceConfig(level=args.level))
        manifest = {
            **world.manifest(),
            "seed": args.seed,
            "trainer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "engine_sha256": hashlib.sha256(
                Path(__file__).parents[1].joinpath("src/duckking/balance.py").read_bytes()
            ).hexdigest(),
            "device": "cpu",
            "cpu": platform.processor(),
            "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
            "envs": args.envs,
            "torch_threads": 1,
            "torch": torch.__version__,
            "policy_kwargs": {
                "net_arch": {"pi": [64, 64], "vf": [64, 64]},
                "log_std_init": float(np.log(args.initial_std)),
            },
            "optimization_reward_scale": args.reward_scale,
            "training_budget": args.steps,
            "validation_seeds": [1_000_000, 1_000_020],
            "test_seeds": [2_000_000, 2_000_000 + args.test_episodes],
            "gate": "success >= 90% of 20 validation episodes, 2 consecutive checks",
            "hyperparameters": {
                "learning_rate": 0.0003,
                "gamma": 0.995,
                "gae_lambda": 0.95,
                "clip_range": 0.2,
                "ent_coef": 0.0005,
                "vf_coef": 0.5,
                "n_steps": 256,
                "batch_size": 128,
                "n_epochs": 10,
            },
        }
        atomic_json(args.output / "manifest.json", manifest)
        status["phase"] = "baseline"
        atomic_json(args.output / "status.json", status)
        baseline = evaluate(
            world, lambda _: np.zeros(3), range(1_000_000, 1_000_020), lambda: cancelled
        )
        if baseline is None:
            status["phase"] = "cancelled"
            return
        atomic_json(args.output / "baseline.json", baseline)
        status["baseline_success_rate"] = baseline["success_rate"]
        with (args.output / "metrics.jsonl").open("w") as f:
            f.write(
                json.dumps(
                    {
                        "steps": 0,
                        "kind": "baseline",
                        "elapsed_s": time.perf_counter() - started,
                        **{k: v for k, v in baseline.items() if k != "results"},
                    }
                )
                + "\n"
            )
        factories = [
            lambda i=i: BalanceEnv(
                args.assets, args.level, args.seed + i * 100000, args.reward_scale
            )
            for i in range(args.envs)
        ]
        vector = SubprocVecEnv(factories, start_method="spawn")
        model = PPO(
            "MlpPolicy",
            vector,
            device="cpu",
            seed=args.seed,
            verbose=0,
            policy_kwargs=manifest["policy_kwargs"],
            **manifest["hyperparameters"],
        )
        # Deterministic step zero is the frozen gait with zero task command.
        torch.nn.init.zeros_(model.policy.action_net.weight)
        torch.nn.init.zeros_(model.policy.action_net.bias)
        export(model, world, args.output / "policy-0.json")
        status["phase"] = "training"
        recorder = Recorder(world, args.output, status, started, args.eval_every, lambda: cancelled)
        model.learn(total_timesteps=args.steps, callback=recorder)
        recorder._on_rollout_start()
        export(model, world, args.output / "last-policy.json")
        model.save(args.output / "last-checkpoint")
        status["steps"] = model.num_timesteps
        if cancelled:
            status["phase"] = "cancelled"
            return
        status["phase"] = "testing"
        atomic_json(args.output / "status.json", status)
        selected = args.output / "best-policy.json"
        if not selected.exists():
            selected = args.output / "last-policy.json"
        policy = BalancePolicy(selected, world.manifest())
        result = evaluate(
            world, policy, range(2_000_000, 2_000_000 + args.test_episodes), lambda: cancelled
        )
        if result:
            atomic_json(args.output / "test.json", {"selected_steps": policy.steps, **result})
        if not cancelled:
            status["phase"] = "baseline-testing"
            atomic_json(args.output / "status.json", status)
            baseline_test = evaluate(
                world,
                lambda _: np.zeros(3),
                range(2_000_000, 2_000_000 + args.test_episodes),
                lambda: cancelled,
            )
            if baseline_test:
                atomic_json(args.output / "baseline-test.json", baseline_test)
        status["phase"] = "cancelled" if cancelled else "completed"
    except Exception as exc:
        status.update(phase="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        finished.set()
        heart.join()
        status["elapsed_s"] = time.perf_counter() - started
        atomic_json(args.output / "status.json", status)
        if vector:
            vector.close()


if __name__ == "__main__":
    main()
