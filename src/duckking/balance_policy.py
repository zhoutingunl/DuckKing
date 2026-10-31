"""Small, validated, non-pickle CPU inference artifact exported from SB3 PPO."""

import json

import numpy as np

from .balance import CONTRACT


class BalancePolicy:
    def __init__(self, path, manifest):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("无法读取 PPO 策略文件") from exc
        if not isinstance(payload, dict):
            raise ValueError("无效 PPO 策略文件")
        if (
            payload.get("contract") != CONTRACT
            or payload.get("model_sha256") != manifest["model_sha256"]
            or payload.get("level") != manifest["config"]["level"]
        ):
            raise ValueError("PPO 策略与模型或关卡不兼容")
        self.layers = []
        width = manifest["observation_size"]
        layers = payload.get("layers")
        if not isinstance(layers, list) or len(layers) != 3:
            raise ValueError("不支持的 PPO 网络结构")
        for layer, outputs in zip(layers, [64, 64, 3], strict=True):
            try:
                w, b = np.array(layer["weight"], np.float32), np.array(layer["bias"], np.float32)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("无效 PPO 权重") from exc
            if (
                w.shape != (outputs, width)
                or b.shape != (outputs,)
                or not np.isfinite(w).all()
                or not np.isfinite(b).all()
            ):
                raise ValueError("无效 PPO 权重")
            self.layers.append((w, b))
            width = len(w)
        self.steps = payload.get("steps")
        if type(self.steps) is not int or self.steps < 0:
            raise ValueError("无效 PPO 训练步数")

    def __call__(self, obs):
        x = np.asarray(obs, np.float32)
        if x.shape != (self.layers[0][0].shape[1],) or not np.isfinite(x).all():
            raise ValueError("无效 PPO 观测")
        for i, (w, b) in enumerate(self.layers):
            x = w @ x + b
            if i < len(self.layers) - 1:
                x = np.tanh(x)
        return np.clip(x, -1, 1)
