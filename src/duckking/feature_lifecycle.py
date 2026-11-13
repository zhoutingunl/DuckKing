"""Decide how a new user command may start, without advancing physics."""

# These are finite courses/performances with a prescribed starting state.
# Reset only when another command is requested, never at a failed finish.
FRESH_TRIAL = frozenset({
    "acrobatics", "sprint_race", "roller_race", "hill_race", "red_light", "tug",
    "climb", "chimney", "runup_roll", "roller_slalom", "roller_glide",
    "terrain_slip", "terrain_rough", "terrain_gale", "terrain_slope", "terrain_step",
    "terrain_stairs", "giant_ball", "running", "long_jump", "stilts", "standup",
    "backflip", "step", "circus",
})
CONTINUOUS = frozenset({
    "movement", "director", "hop", "flamingo", "basketball", "emotions", "dock",
    "dock_standing", "footsteps", "senses", "tof", "theremin", "search", "soccer",
    "navigation", "swing",
})


def start_plan(world, capability, previous, state, action):
    if capability not in FRESH_TRIAL | CONTINUOUS:
        raise ValueError("当前场景尚未配置连续动作，请重新准备场景")
    if capability in FRESH_TRIAL:
        if previous.get("status", "idle") != "idle":
            return {"mode": "restart", "reason": "这个动作从起点开始，正在准备新一轮。"}
        return {"mode": "continue", "reason": ""}
    if hook := getattr(world, "start_condition", None):
        if plan := hook(action):
            return plan
    if capability == "swing":
        if previous.get("status") == "failed":
            return {"mode": "restart", "reason": "正在恢复场景，准备执行新指令。"}
    elif any(duck.get("fallen") for duck in state.get("ducks", [])):
        return {"mode": "restart", "reason": "小鸭失稳，正在自动恢复起点。"}
    return {"mode": "continue", "reason": ""}
