#!/usr/bin/env python
"""局内战斗循环（boss_mode / missile_hunt 共用）。

闪击类玩法进局后的通用流程:
    点右下角技能 → 阵亡复活(钻石) → 装备UP选择(取默认项) → 结算页继续

各用例只决定「什么算战斗结束」，传一个 out_of_battle(sc) 回调即可:
    - BOSS 闪击: 回到 BOSS 列表页(立即) / 连续 3 次停在站内页
    - 导弹猎场: 回到活动关卡页

⚠ 战斗间隙会短暂闪过「战斗外」页面，所以连续 N 次仍判定为真才算收工
⚠ 技能优先用模板 battle_skill(窗口尺寸变化后仍自适应)，没命中再退坐标兜底
⚠ 技能要**周期性**点(默认每 5.2s 一次)，不是进局点一下:
    进局先过「资源加载中」页，此时盲点一次技能是空点；只点一次的老写法就再也不会补点
    → 表现为「技能没按到」。周期点击天然把这一下补回来。
⚠ 自检会临时改小 FIGHT_TIMEOUT 来控预算，所以用例侧要留同名模块常量、调用时读取
"""
from __future__ import annotations

import time
from typing import Callable

from wb.kit import log, nap

TH = 0.85
SKILL_XY = (740, 1300)      # 局内右下角技能键(与 battle_watch.py 同源标定)
SKILL_PERIOD = 5.2          # 技能点击间隔(秒): 技能冷却约 5s，按 5.2s 卡节奏连点
#   ↑ 技能要**按周期反复点**，不是进局点一下: 进局先过「资源加载中」页，那一下是空点。
#   templates/battle_skill.png 裁自《导弹猎场》局内真帧(601x1143 → 按画布高比归一到 845 基准)，
#   845/812 两种窗口下实测 1.000 / 0.998，且全 shots 库无≥ 0.85 的误命中；
#   万一其他模式换皮→匹配不到就用 SKILL_XY 兜底(实测落在按钮半径 52px 内)。
FIGHT_TIMEOUT = 480         # 单轮最长等待: 每轮 40~80s + 加载缓冲
POLL = 2.0                  # 基础轮询间隔(判弹窗/判离开战斗的粒度)


def find(sc, name: str, th: float = TH):
    """模板缺失时返回 None(不炸)，便于逐步补模板。"""
    try:
        return sc.find(name, th)
    except FileNotFoundError:
        return None


def fight(sc, out_of_battle: Callable, *, skill_xy: tuple = SKILL_XY,
          skill_period: float = SKILL_PERIOD,
          timeout: float = FIGHT_TIMEOUT, label: str = "局内") -> tuple[bool, int, int]:
    """跑完一轮局内，直到 out_of_battle(sc) 连续命中够次数。

    out_of_battle(sc) 返回「看着已离开战斗时需要的连续命中次数」：
        0 = 还在战斗里；1 = 确认无疑(如回到列表页，立即收工)；3 = 需连续 3 次
        （战斗间隙会短暂闪过战斗外页面，所以要防抖）

    局内每 skill_period 秒点一次右下角技能(不是只点一次)；复活/结算后立即补点。
    返回 (是否跑完, 结算页轮次, 复活次数)；超时返回 (False, 轮次, 复活次数)。
    超时会留证截图 fight_timeout。
    """
    rounds = revives = equipups = 0
    hits = 0
    next_skill = 0.0                        # 0 → 进局第一轮就点
    t0 = time.time()
    while time.time() - t0 < timeout:
        snooze = POLL                       # 默认轮询间隔(弹窗/离开战斗的判定粒度)
        now = time.time()
        rv = find(sc, "boss_revive_diamond")
        eq = find(sc, "boss_equipup_title")     # 用标题判定: 两个弹窗的绿「确认」长得像
        nx = find(sc, "boss_result_next")
        if rv is not None:
            revives += 1
            log(f"阵亡 → 复活(钻石20) {rv}")
            sc.click(rv, "复活")
            nap(2.2)
            next_skill = 0.0                    # 复活后立刻补一次技能
        elif eq is not None:
            equipups += 1
            ok = find(sc, "boss_equipup_ok") or eq
            log(f"装备UP选择弹窗 → 确认(取默认选中项) {ok}")
            sc.click(ok, "装备UP-确认")
            nap(2.5)
        elif nx is not None:
            rounds += 1
            log(f"结算页 → 继续 {nx}  (第 {rounds} 轮)")
            sc.click(nx, "继续")
            nap(3.5)
            next_skill = 0.0                    # 新一轮开始，立即点技能
            hits = 0                            # 防抖计数清零
        elif (need := out_of_battle(sc)):
            hits += 1
            if hits >= need:
                log(f"{label}结束 (结算页 {rounds} 张 / 复活 {revives} / 装备UP {equipups})")
                return True, rounds, revives
        else:
            hits = 0
            if now >= next_skill:               # 周期性点技能(进局空点也能被下一次补回来)
                sk = find(sc, "battle_skill", 0.90)
                if sk is not None:
                    sc.click(sk, "右下角技能(模板)")
                else:
                    # 兜底坐标也是基准坐标: 窗口小于基准时会点到窗口外(601 宽时 x=740 直接出界)
                    sc.click_base(skill_xy[0], skill_xy[1], "右下角技能(坐标兜底)")
                next_skill = time.time() + skill_period
            # 距下次点技能不到一个基础轮询间隔就睡到点，否则按基础间隔轮询
            snooze = min(POLL, max(0.4, next_skill - time.time()))
        nap(snooze)
    log(f"{label}等待超时(结算 {rounds} / 复活 {revives} / 装备UP {equipups})")
    sc.shot("fight_timeout")
    return False, rounds, revives
