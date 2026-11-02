"""Optional tests with the isolated CPU training interpreter, no cloud accounts."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch
from stable_baselines3 import PPO
from train_seesaw import Env, evaluate, export, warm_start

from duckking.seesaw import OBSERVATION_SIZE, SeesawWorld
from duckking.seesaw_policy import SeesawPolicy


class SeesawTrainerChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        cls.assets = Path(__file__).resolve().parents[1] / "external"
        cls.world = SeesawWorld(cls.assets)

    def model(self):
        with patch("train_seesaw.SeesawWorld", return_value=self.world):
            env = Env(self.assets, 42)
        return PPO("MlpPolicy", env, n_steps=16, batch_size=16, n_epochs=1, seed=42, device="cpu")

    def test_real_update_export_parity_and_terminal_reward_scaling(self):
        model = self.model()
        model.learn(32)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            exported = export(model, self.world, path)
            self.assertEqual(exported.steps, 32)
            obs = self.world.reset(99)
            for _ in range(10):
                self.assertEqual(exported(obs), int(model.predict(obs, deterministic=True)[0]))
                obs, *_ = self.world.step(exported(obs))
        env = model.get_env().envs[0].env
        env.reset()
        ended = False
        while not ended:
            _, scaled, ended, truncated, info = env.step(0)
            self.assertFalse(truncated)
            self.assertAlmostEqual(scaled, 0.1 * sum(info["reward_terms"].values()))

    def test_curriculum_preserves_actor_and_records_lineage_not_zero_steps(self):
        model = self.model()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            export(model, self.world, source)
            payload = json.loads(source.read_text())
            payload.update(
                contract="seesaw-v2-settle",
                steps=49152,
                model_sha256="0261fe9099449a7f8ca2c338cd01d7eaa3f8205833bed4380c833e7b42875ce3",
            )
            payload["layers"][0]["weight"] = [row[:14] for row in payload["layers"][0]["weight"]]
            source.write_text(json.dumps(payload))
            identity = warm_start(model, source, self.world)
            self.assertEqual(identity["source_steps"], 49152)
            target = Path(directory) / "new.json"
            export(model, self.world, target)
            policy = SeesawPolicy(target, self.world.manifest())
            self.assertEqual(policy.steps, 49152)
            rng = np.random.default_rng(7)
            for obs in rng.normal(size=(32, OBSERVATION_SIZE)).astype(np.float32):
                changed = obs.copy()
                changed[14:] += 100
                self.assertEqual(policy(obs), policy(changed))
            payload["model_sha256"] = "incorrect"
            source.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                warm_start(model, source, self.world)

    def test_driven_actor_transfer_drops_period_column_without_inventing_new_steps(self):
        model = self.model()
        source = self.assets.parent / "training/seesaw_results/driven-v3/policy.json"
        payload = json.loads(source.read_text())
        identity = warm_start(model, source, self.world)
        self.assertEqual(identity["source_steps"], 180224)
        self.assertEqual(identity["kind"], "passive_docking_transfer")
        with tempfile.TemporaryDirectory() as directory:
            policy = export(model, self.world, Path(directory) / "policy.json")
            self.assertEqual(policy.steps, 180224)
            for obs in (
                np.random.default_rng(9).normal(size=(32, OBSERVATION_SIZE)).astype(np.float32)
            ):
                x = np.append(obs, np.float32(0))
                for i, layer in enumerate(payload["layers"]):
                    x = np.array(layer["weight"], np.float32) @ x + np.array(
                        layer["bias"], np.float32
                    )
                    if i < 2:
                        x = np.tanh(x)
                self.assertEqual(policy(obs), int(np.argmax(x)))

    def test_evaluation_counts_actual_terminal_results_and_cancels_before_stepping(self):
        result = evaluate(self.world, lambda _: 0, [100, 101])
        self.assertEqual(result["episodes"], 2)
        self.assertEqual(result["successes"], sum(r["success"] for r in result["results"]))
        self.assertEqual([r["seed"] for r in result["results"]], [100, 101])
        with self.assertRaises(InterruptedError):
            evaluate(self.world, lambda _: 0, range(100), lambda: True)


if __name__ == "__main__":
    unittest.main()
