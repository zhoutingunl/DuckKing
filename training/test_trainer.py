"""Optional CPU-training checks; run with the isolated training interpreter."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from train_balance import BalanceEnv, evaluate, export

from duckking.balance import BalanceConfig, BalanceWorld
from duckking.balance_policy import BalancePolicy


class TrainerChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        cls.assets = Path(__file__).resolve().parents[1] / "external"
        cls.world = BalanceWorld(cls.assets, BalanceConfig())

    def test_export_matches_sb3_after_real_cpu_updates(self):
        def create(assets, config):
            return BalanceWorld(
                assets, config, (self.world.model, self.world.fingerprint), self.world.session
            )

        with patch("train_balance.BalanceWorld", create):
            vector = DummyVecEnv([lambda: BalanceEnv(self.assets, 1, 42)])
        try:
            model = PPO(
                "MlpPolicy",
                vector,
                device="cpu",
                n_steps=16,
                batch_size=16,
                n_epochs=1,
                seed=12,
                policy_kwargs={"net_arch": {"pi": [64, 64], "vf": [64, 64]}},
            )
            model.learn(32)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "policy.json"
                export(model, self.world, path)
                policy = BalancePolicy(path, self.world.manifest())
                self.assertEqual(policy.steps, 32)
                obs = self.world.reset(123)
                for _ in range(10):
                    expected, _ = model.predict(obs, deterministic=True)
                    np.testing.assert_allclose(policy(obs), expected, atol=2e-6)
                    obs, *_ = self.world.step(policy(obs))
        finally:
            vector.close()

    def test_evaluation_uses_full_terminal_outcome_and_can_cancel(self):
        result = evaluate(self.world, lambda _: np.zeros(3), [100, 101])
        self.assertEqual(result["episodes"], 2)
        self.assertEqual([r["seed"] for r in result["results"]], [100, 101])
        self.assertEqual(result["successes"], sum(r["success"] for r in result["results"]))
        self.assertLessEqual(result["ci95"][0], result["success_rate"])
        self.assertGreaterEqual(result["ci95"][1], result["success_rate"])
        self.assertIsNone(evaluate(self.world, lambda _: np.zeros(3), [102], lambda: True))

    def test_optimization_scale_does_not_change_reported_reward_or_terminal_semantics(self):
        with patch("train_balance.BalanceWorld", return_value=self.world):
            env = BalanceEnv(self.assets, 1, 0, reward_scale=0.05)
        env.reset(seed=99)
        ended = False
        while not ended:
            _, scaled, ended, truncated, info = env.step(np.zeros(3))
            self.assertFalse(truncated)
            self.assertAlmostEqual(scaled, 0.05 * sum(info["reward_terms"].values()))
        self.assertIsNotNone(info["reason"])


if __name__ == "__main__":
    unittest.main()
