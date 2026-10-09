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
⚠ 节拍必须**拆成两拍**，否则追不上 5.2s(2026-10-09 实测):
    实测**单个模板匹配 ~0.8s**(多尺度)，而一轮要判「复活/装备UP/结算/技能/离开」≈ 9 个模板
    ≈ 6.9s > 5.2s 周期 → 旧写法(先全部识别完再看要不要点技能)实际间隔被拖到 12s。
    现在：
      ① **技能节拍优先**：到点就直接点(纯点击 ~0.05s)，不先做识别；
      ② 技能键位置**缓存**(局内固定)，只试一次匹配，不中就永久走兜底坐标；
      ③ `out_of_battle` **隔轮做**(它一次要查 5 个模板)；弹窗判定每轮都做，一项不漏。
    → 单轮开销降到 ~4.2s < 5.2s，节拍才真按 5.2s 走。
⚠ 进局后先等 SKILL_FIRST(0.5s) 再点第一下: 开局还在「资源加载中」页，早点是空点。
⚠ 自检会临时改小 FIGHT_TIMEOUT 来控预算，所以用例侧要留同名模块常量、调用时读取
"""
from __future__ import annotations

import time
from typing import Callable

from wb.kit import log, nap

TH = 0.85
SKILL_XY = (740, 1300)      # 局内右下角技能键(与 battle_watch.py 同源标定)
SKILL_PERIOD = 5.2          # 技能点击间隔(秒): 技能冷却约 5s，按 5.2s 卡节奏连点
SKILL_FIRST = 0.5           # 进局后先等 0.5s 再点第一下(等「资源加载中」页翻过去)
SKILL_TH = 0.90             # battle_skill 的阈值(比 TH 严一点，少误命中)
BATTLE_TPLS = ("boss_revive_diamond", "boss_equipup_title", "boss_result_next")
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


def look_battle(sc) -> dict:
    """一次抓帧批量匹配局内的 3 个弹窗模板(复活/装备UP/结算)。

    逐个 find 要抓 3 次屏；look 只抓一次。缺模板时退回逐个查(慢但不炸)。
    注意: 不把 battle_skill 放进来 —— 它只试一次并缓存(见 fight)，
    否则每轮多花 ~0.8s，单轮超过 5.2s 周期就追不上节拍了。
    """
    try:
        return sc.look(*BATTLE_TPLS)
    except FileNotFoundError:
        return {n: find(sc, n) for n in BATTLE_TPLS}


def fight(sc, out_of_battle: Callable, *, skill_xy: tuple = SKILL_XY,
          skill_period: float = SKILL_PERIOD,
          timeout: float = FIGHT_TIMEOUT, label: str = "局内") -> tuple[bool, int, int]:
    """跑完一轮局内，直到 out_of_battle(sc) 连续命中够次数。

    out_of_battle(sc) 返回「看着已离开战斗时需要的连续命中次数」：
        0 = 还在战斗里；1 = 确认无疑(如回到列表页，立即收工)；3 = 需连续 3 次
        （战斗间隙会短暂闪过战斗外页面，所以要防抖）

    局内每 skill_period 秒点一次右下角技能(不是只点一次)；复活/结算后 0.5s 补点。
    返回 (是否跑完, 结算页轮次, 复活次数)；超时返回 (False, 轮次, 复活次数)。
    超时会留证截图 fight_timeout。

    节拍与识别的分工(单模板匹配 ~0.8s，一轮预算 <5.2s):
        ① 技能: 到点先点(纯点击)，位置缓存在 sk_hit，只试一次匹配，不中永久兜底
        ② 弹窗: 每轮都判(复活/装备UP/结算)，一项不漏
        ③ 离开战斗: 隔轮判(out_of_battle 一次要查 5 个模板 ~3.7s)
    """
    rounds = revives = equipups = 0
    hits = 0
    next_skill = time.time() + SKILL_FIRST   # 进局先等 0.5s(资源加载中页会吞掉第一下)
    sk_hit = None                            # None=未试 / ""=试过没中(永久兜底坐标)
    last_dialog = False
    tick = 0                                 # 离开战斗判定隔轮做的开关
    t0 = time.time()
    while time.time() - t0 < timeout:
        now = time.time()
        # ① 技能节拍优先: 到点且「上轮没见弹窗、也没判到已离开战斗」→ 直接点
        #    (not hits 很关键: 一旦 out_of_battle 报过 1 次，就别再往 (721,1288) 盲点 ——
        #     自检 2026-10-09 抓到: 战斗已结束还多点两下，而那个点压在邻近按钮上)
        if now >= next_skill and not last_dialog and not hits:
            if sk_hit:
                sc.click(sk_hit, "右下角技能(模板·缓存)")
            else:
                # 兜底坐标是基准坐标: 窗口小于基准时会点到窗口外(601 宽时 x=740 直接出界)
                sc.click_base(skill_xy[0], skill_xy[1], "右下角技能(坐标兜底)")
            # 从**本次点击时刻**递推: 识别耗时不再一期一期累积进间隔
            next_skill = now + skill_period
        # ② 弹窗判定(每轮 1 次抓帧、3 个模板)
        st = look_battle(sc)
        rv = st["boss_revive_diamond"]
        eq = st["boss_equipup_title"]       # 用标题判定: 两个弹窗的绿「确认」长得像
        nx = st["boss_result_next"]
        last_dialog = rv is not None or eq is not None or nx is not None
        if rv is not None:
            revives += 1
            log(f"阵亡 → 复活(钻石20) {rv}")
            sc.click(rv, "复活")
            nap(2.2)
            next_skill = time.time() + SKILL_FIRST   # 复活后 0.5s 补一次技能
            hits = 0
            tick = 0                                # 下轮必须复查是否还在局内，才允许再点技能
        elif eq is not None:
            equipups += 1
            ok = find(sc, "boss_equipup_ok") or eq
            log(f"装备UP选择弹窗 → 确认(取默认选中项) {ok}")
            sc.click(ok, "装备UP-确认")
            nap(2.5)
            hits = 0
            tick = 0                                # 同上: 弹窗处理后先复查是否还在局内
        elif nx is not None:
            rounds += 1
            log(f"结算页 → 继续 {nx}  (第 {rounds} 轮)")
            sc.click(nx, "继续")
            nap(3.5)
            next_skill = time.time() + SKILL_FIRST   # 新一轮开始，0.5s 后点技能
            hits = 0                            # 防抖计数清零
            tick = 0                            # 同上: 结算后先复查是否还在局内，别盲点技能
        else:
            if sk_hit is None:                  # 技能键只试一次匹配，中不中都记住
                sk_hit = find(sc, "battle_skill", SKILL_TH) or ""
                log("技能键模板" + (f"命中 {sk_hit[:2]}(缓存)" if sk_hit
                                  else "不适用 → 以后都走兜底坐标"))
            tick ^= 1
            if tick:                            # 隔轮判「是否已离开战斗」(这步最贵)
                need = out_of_battle(sc)
                if need:
                    hits += 1
                    if hits >= need:
                        log(f"{label}结束 (结算页 {rounds} 张 / 复活 {revives} / 装备UP {equipups})")
                        return True, rounds, revives
                else:
                    hits = 0
        # ≤一个基础轮询间隔，且不越过下次点技能的时点
        nap(min(POLL, max(0.4, next_skill - time.time())))
    log(f"{label}等待超时(结算 {rounds} / 复活 {revives} / 装备UP {equipups})")
    sc.shot("fight_timeout")
    return False, rounds, revives
