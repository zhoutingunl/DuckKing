"""Bounded local look-around/yawn choreography, inspired by official idle_head.rs.

This is a DuckKing adaptation, not the robotd autonomous/perception stack.
Opt-in; explicit stop disables it, and an active action always owns the joints.
"""

import math


def yawn_frame(t):
    opening = math.sin(math.pi * min(1, max(0, t / 4))) ** 2
    return -0.22 * opening, 0.48 * opening


class IdleBehaviour:
    def __init__(self, backend):
        self.b = backend
        self.enabled = False
        self.resume_at = math.inf
        self.phase = "off"
        self.mouth = backend.model.actuator("mouth").id

    def pause(self):
        self.resume_at = math.inf
        self.phase = "paused" if self.enabled else "off"
        self.b.data.ctrl[self.mouth] = 0

    def stop(self):
        self.b.data.ctrl[self.mouth] = 0
        self.resume_at = self.b.data.time + 2 if self.enabled else math.inf
        self.phase = "waiting" if self.enabled else "off"

    def tick(self):
        t = self.b.data.time - self.resume_at
        if not self.enabled or t < 0:
            return
        driver = self.b.drivers[0]
        # Never continue expressive behaviour on a fallen robot.
        if self.b.data.xmat[driver.body, 8] < 0.8:
            self.enabled = False
            driver.command[:] = 0
            self.stop()
            return
        cycle = t % 20
        fade = min(t / 0.6, 1)
        driver.command[3:7] = 0
        if 12 <= cycle < 16:
            pitch, mouth = yawn_frame(cycle - 12)
            driver.command[4] = pitch
            self.b.data.ctrl[self.mouth] = mouth
            self.phase = "yawn"
        else:
            # Smooth glances, each with a hold; varying phases avoid clockwork sweeps.
            index = int(t // 3)
            mix = min((t % 3) / 0.8, 1)
            mix = mix * mix * (3 - 2 * mix)

            def gaze(i):
                return (0.28 * math.sin(i * 2.4), 0.10 * math.sin(i * 1.7))

            old, new = gaze(index - 1), gaze(index)
            driver.command[5] = fade * (old[0] * (1 - mix) + new[0] * mix)
            driver.command[6] = fade * (old[1] * (1 - mix) + new[1] * mix)
            driver.command[4] = fade * 0.045 * math.sin(t * 0.7)
            self.b.data.ctrl[self.mouth] = 0
            self.phase = "look_around"

    def snapshot(self):
        return {
            "enabled": self.enabled,
            "phase": self.phase,
            "source": "local_choreography_official_inspired",
        }
