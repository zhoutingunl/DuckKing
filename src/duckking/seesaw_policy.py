"""Validated JSON inference, without torch or pickle on the web server."""

import json

import numpy as np

from .seesaw import CONTRACT, OBSERVATION_SIZE


class SeesawPolicy:
    def __init__(self, path, manifest):
        try:
            value = json.loads(path.read_text())
            if (
                value["contract"] != CONTRACT
                or value["model_sha256"] != manifest["model_sha256"]
                or value["action_type"] != "categorical"
            ):
                raise ValueError("策略与跷跷板模型或控制契约不兼容")
            self.steps = value["steps"]
            if type(self.steps) is not int or self.steps < 0 or len(value["layers"]) != 3:
                raise ValueError("无效训练步数或网络结构")
            width = manifest["observation_size"]
            self.layers = []
            for layer, outputs in zip(value["layers"], [64, 64, 3], strict=True):
                w, b = np.array(layer["weight"], np.float32), np.array(layer["bias"], np.float32)
                if (
                    w.shape != (outputs, width)
                    or b.shape != (outputs,)
                    or not np.isfinite(w).all()
                    or not np.isfinite(b).all()
                ):
                    raise ValueError("无效策略权重")
                self.layers.append((w, b))
                width = outputs
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("无法读取有效跷跷板策略") from exc

    def __call__(self, obs):
        x = np.asarray(obs, np.float32)
        if x.shape != (OBSERVATION_SIZE,) or not np.isfinite(x).all():
            raise ValueError("无效跷跷板观测")
        for i, (w, b) in enumerate(self.layers):
            with np.errstate(over="ignore", invalid="ignore"):
                x = w @ x + b
            if not np.isfinite(x).all():
                raise ValueError("跷跷板策略推理出现非有限值")
            if i < 2:
                x = np.tanh(x)
        return int(np.argmax(x))
