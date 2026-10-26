"""Explicit one-time setup using a platform API key file; never run on page load."""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import httpx

from .config import Settings, provision

PROMPT = """你是 DuckKing，一个友好的虚拟机器人鸭子，中文名字叫鸭王。
用简短中文回答，一般不超过两句话。用户要求点头、前进、左转、右转或停止时，必须调用对应设备工具，
不要仅口头答应。工具返回完成后才能说完成；取消、失败或未连接时如实说明。
可用工具为 duck_nod、duck_walk_short、duck_turn_left、duck_turn_right、duck_stop、duck_get_status、
duck_flash_step、duck_bear_shake。
前进调用 duck_walk_short，左转调用 duck_turn_left，右转调用 duck_turn_right，停止调用 duck_stop。
一句话包含多个动作时，严格按用户的顺序逐个调用，每个工具完成后才调用下一个，禁止并行执行。
例如“向前走再向左转再向右转”，依次调用 duck_walk_short、duck_turn_left、duck_turn_right。
某一步失败或取消后停止后续步骤，如实说明。普通转向不能替换为闪身步或其他舞步，不保证精确角度。
用户说“闪身步”时调用 duck_flash_step；说“狗熊哆嗦毛”或“抖抖毛”时调用 duck_bear_shake。
这两个动作是机器人改编舞步，必须等待工具返回，再说明是否完成。
在提供场景工具的物理实验室中：单鸭踢球先用 duck_set_scene(scene=ball)，双鸭互动用 scene=duo。
场景切换会复位，所以同一场景内不要每次都切换；可先调用 duck_get_status 查看。
用户说左脚踢球调用 duck_kick(foot=left)，右脚踢球调用 foot=right；没指定脚时先询问。
每次定点踢球会把球摆到所选脚前，然后才执行策略，不是自主找球。等待工具确认脚球接触和位移，未踢中就如实说明。
坐下用 duck_sit，站起来用 duck_stand；默认鸭 A，可指定 target=b 或 both。
坐着可以点头；行走、转向或踢球前先调用 duck_stand 并等待确认站稳。
坐站仅支持 ball/duo/skills 物理场景；没有提供工具时不能声称已执行。
发现同伴用 duck_find_companion，一起走用 duck_duo_walk。
相向碰面或碰撞用 duck_collide，合唱用 duck_chorus。
拿东西/搬运：先确认当前是 carry 场景。
按顺序 duck_pick_up 夹起、duck_carry 搬运、duck_put_down 放下。
每一步等待 verified=true 才继续；抓空、滑落、未落稳都如实报告失败，不声称已完成。
工具名、scene、carry、verified、phase 等字段只用于内部判断，不要读给用户。
通常用一句简短自然中文确认结果，不逐条复述内部检查，不说 verified 为 true。
当前只支持固定取物架上的轻质小棒，新增嘴部是实验性仿真，不是手或翅膀抓取，也不支持任意物品。
合唱是本地合成双声部，需要浏览器启用声音，不是你在云端生成的歌声；工具完成不代表扬声器一定播放。
发现同伴使用仿真位置和视线判定，不是视觉识别或真实蓝牙。没有相应工具时说明当前页面不支持，不能假装执行。
后退用 duck_backward；左右横移用 duck_strafe_left / duck_strafe_right，不要改成转向或闪身步。
摇头用 duck_shake_head，歪头用 duck_tilt_head。
前滚翻、打哈欠、自然待机、低头啄取先用 duck_set_scene 切到 skills 动作练习场。
已在此场景不重复切换。
分别调用 duck_roulade、duck_yawn、duck_idle_on、duck_ground_pick；关闭自然待机用 duck_idle_off。
前滚翻失败不能声称已完成。低头啄取只让嘴尖接近地面，不夹持物品，不能说已经拿到了物品。
轮滑先切到 rollers 场景，再用 duck_skate；轮滑下蹲用 duck_roller_crouch。
自然待机为本地程序，不代表看到了真实物体；当前未接入摄像头物体识别。
以上需要相应工具；没有工具时不能假装执行。
现场互动时不解释工具名称或内部机制，执行前简短确认即可，完成后一句结果加短笑话，总计尽量不超过三十字。
轻松聊天时可以偶尔短促地说一声“嘎”，不要每句话都加，不影响听清指令和结果。
现场互动节目提供额外工具时，先通过 duck_get_status 查看当前节目与任务状态。
临场小导演用 duck_direct 将故事编排为已有动作，用户说只用头就 head_only=true；
用户临时修改时提交完整替代计划。不是学习新策略；等待工具返回后才说完成。
快递员用 duck_delivery；暂停不松嘴，继续要从实际阶段恢复，不能重头再抓。
四鸭指挥用 duck_conduct；队列受理只说已安排，不说已经唱完。queue 只替换后续歌手。
暗号用 duck_recipe：先 draft 复述，等用户下一轮明确确认才 confirm；编辑要重新确认。
踢球教练用 duck_coach，observe 只看，prepare 明确摆球，kick 才踢，不得用旧 duck_kick 偷偷摆球。
用户要求设置或修改游戏规则时，必须调用 duck_game configure 保存规则，不能只口头答应。
鸭王说游戏只用 duck_game 执行动作，不能通过其他工具绕过口令规则；紧急停止永远有效。
橡皮鸭追问每一轮先用 duck_discuss 记录事实与问题，再只问这个问题；
事实被更正时 replace_facts=true 撤回旧判断。
专注提醒用 duck_focus，延期用 extend，取消用 cancel；受理后只说已安排，不说到期。
音色用 duck_voice_style，只选择工具描述中已配置的音色；修改会在下一轮输入生效。
所有表演仍为本地 MuJoCo 物理任务，音乐为本地合成，禁止说是云端现场生成歌曲。
四鸭发布会 stage 舞台只使用 duck_stage_gather 集结排队、duck_stage_roll 点名前滚翻归位、
duck_stage_dance 全体闪身步然后抖毛，不要切换场景或调用单鸭旧工具。
“这只”“这些”“选中的鸭子”用 member=selected（整个屏幕多选集合，未选中时请先选择）。
“最左边”用 member=leftmost，A—D 用 a/b/c/d。
排队和翻滚先等待工具实际完成，再继续下一项。
你控制的是本地虚拟鸭子，不要声称已经制造或操控实体硬件。"""


def read_key(path: Path) -> str:
    return path.expanduser().read_text().strip()


async def setup_device(
    settings: Settings, key_file: Path, agent_id=None, model_id=None, http=None, sync_prompt=False,
):
    key = await asyncio.to_thread(read_key, key_file)
    if not key or "\n" in key:
        raise ValueError("API Key 文件应仅包含一行原始平台 API Key")
    own_client = http is None
    http = http or httpx.AsyncClient(timeout=20)
    try:

        async def api(method, path, body=None):
            response = await http.request(
                method,
                "https://xrobo.qiniu.com" + path,
                headers={"Authorization": f"Bearer {key}"},
                json=body,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("code") != 0:
                raise ValueError(f"平台 API 返回业务错误 {data.get('code', 'unknown')}")
            return data.get("data")

        agents = await api("GET", "/xiaozhi/agent/list")
        if not isinstance(agents, list):
            raise ValueError("智能体列表格式异常")
        if agent_id:
            if not any(a.get("id") == agent_id for a in agents):
                raise ValueError("指定智能体不在该账号的列表中")
        else:
            matches = [a for a in agents if a.get("agentName") == "DuckKing"]
            if len(matches) > 1:
                raise ValueError("有多个同名 DuckKing 智能体，请指定 --agent-id")
            if matches:
                agent_id = matches[0]["id"]
            else:
                if sync_prompt:
                    raise ValueError("未找到已有 DuckKing 智能体")
                body = {
                    "agentName": "DuckKing",
                    "assistantName": "鸭王",
                    "langCode": "zh",
                    "intentModelId": "Intent_function_call",
                    "memModelId": "Memory_nomem",
                    "systemPrompt": PROMPT,
                }
                if model_id:
                    body["llmModelId"] = model_id
                agent_id = await api("POST", "/xiaozhi/agent", body)
                if not isinstance(agent_id, str) or not agent_id:
                    raise ValueError("创建智能体未返回有效 ID")
        if sync_prompt:
            selected = next(a for a in agents if a.get("id") == agent_id)
            if selected.get("agentName") != "DuckKing":
                raise ValueError("仅允许同步 DuckKing 专用智能体的提示词")
            before = await api("GET", f"/xiaozhi/agent/{agent_id}")
            if not isinstance(before, dict) or not isinstance(before.get("systemPrompt"), str):
                raise ValueError("无法读取原提示词，未进行更新")
            if before["systemPrompt"] == PROMPT:
                return {"status": "prompt_current"}
            settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            backup = settings.data_dir / f"prompt-backup-{time.time_ns()}.txt"
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(before["systemPrompt"])
            await api("PUT", f"/xiaozhi/agent/{agent_id}", {"systemPrompt": PROMPT})
            after = await api("GET", f"/xiaozhi/agent/{agent_id}")
            if not isinstance(after, dict) or after.get("systemPrompt") != PROMPT:
                raise ValueError("提示词更新后校验失败，请检查平台配置")
            return {"status": "prompt_updated"}
        config = await provision(settings, http)
        code = config.get("activation", {}).get("code")
        if code:
            await api("POST", f"/xiaozhi/device/bind/{agent_id}/{code}", {})
            config = await provision(settings, http)
        else:
            # Never silently migrate an already-bound device or its chat history.
            return {
                "status": "already_bound",
                "agent_created_or_selected": agent_id,
                "message": "设备已绑定，未更改其关联智能体",
            }
        ready = bool(config.get("websocket", {}).get("token")) and not config.get("activation")
        result = {"status": "ready" if ready else "binding_pending", "agent_id": agent_id}
        target = settings.data_dir / "onboarding.json"
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(result, stream)
        return result
    finally:
        if own_client:
            await http.aclose()


def main():
    parser = argparse.ArgumentParser(description="Create/select DuckKing and bind this device")
    parser.add_argument("--key-file", type=Path, default=Path("~/.secrets/lingxi"))
    parser.add_argument("--room", default="1", help="房间编号，不能超过 DUCKKING_MAX_ROOMS")
    parser.add_argument("--agent-id")
    parser.add_argument("--model-id")
    parser.add_argument(
        "--sync-prompt", action="store_true",
        help="备份并同步已有 DuckKing 智能体的提示词，不创建或重新绑定设备",
    )
    args = parser.parse_args()
    try:
        result = asyncio.run(
            setup_device(
                Settings.load().for_room(args.room), args.key_file,
                agent_id=args.agent_id, model_id=args.model_id,
                sync_prompt=args.sync_prompt,
            )
        )
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        raise SystemExit(
            f"设备设置失败（{type(exc).__name__}）。请检查 Key、网络和平台配置。"
        ) from None


if __name__ == "__main__":
    main()
